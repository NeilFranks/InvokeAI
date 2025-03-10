"""SAMPLING ONLY."""

from functools import partial

import numpy as np
import torch
from tqdm import tqdm

from ...util import choose_torch_device
from ..diffusionmodules.util import noise_like
from .sampler import Sampler
from .shared_invokeai_diffusion import InvokeAIDiffuserComponent


class PLMSSampler(Sampler):
    def __init__(self, model, schedule="linear", device=None, **kwargs):
        super().__init__(model, schedule, model.num_timesteps, device)

    def prepare_to_sample(self, t_enc, **kwargs):
        super().prepare_to_sample(t_enc, **kwargs)

        extra_conditioning_info = kwargs.get("extra_conditioning_info", None)
        all_timesteps_count = kwargs.get("all_timesteps_count", t_enc)

        if (
            extra_conditioning_info is not None
            and extra_conditioning_info.wants_cross_attention_control
        ):
            self.invokeai_diffuser.override_cross_attention(
                extra_conditioning_info, step_count=all_timesteps_count
            )
        else:
            self.invokeai_diffuser.restore_default_cross_attention()

    # this is the essential routine
    @torch.no_grad()
    def p_sample(
        self,
        x,  # image, called 'img' elsewhere
        c,  # conditioning, called 'cond' elsewhere
        t,  # timesteps, called 'ts' elsewhere
        index,
        repeat_noise=False,
        use_original_steps=False,
        quantize_denoised=False,
        temperature=1.0,
        noise_dropout=0.0,
        score_corrector=None,
        corrector_kwargs=None,
        unconditional_guidance_scale=1.0,
        unconditional_conditioning=None,
        old_eps=[],
        t_next=None,
        step_count: int = 1000,  # total number of steps
        **kwargs,
    ):
        b, *_, device = *x.shape, x.device

        def get_model_output(x, t):
            if (
                unconditional_conditioning is None
                or unconditional_guidance_scale == 1.0
            ):
                # damian0815 would like to know when/if this code path is used
                e_t = self.model.apply_model(x, t, c)
            else:
                # step_index counts in the opposite direction to index
                step_index = step_count - (index + 1)
                e_t = self.invokeai_diffuser.do_diffusion_step(
                    x,
                    t,
                    unconditional_conditioning,
                    c,
                    unconditional_guidance_scale,
                    step_index=step_index,
                )
            if score_corrector is not None:
                assert self.model.parameterization == "eps"
                e_t = score_corrector.modify_score(
                    self.model, e_t, x, t, c, **corrector_kwargs
                )

            return e_t

        alphas = self.model.alphas_cumprod if use_original_steps else self.ddim_alphas
        alphas_prev = (
            self.model.alphas_cumprod_prev
            if use_original_steps
            else self.ddim_alphas_prev
        )
        sqrt_one_minus_alphas = (
            self.model.sqrt_one_minus_alphas_cumprod
            if use_original_steps
            else self.ddim_sqrt_one_minus_alphas
        )
        sigmas = (
            self.model.ddim_sigmas_for_original_num_steps
            if use_original_steps
            else self.ddim_sigmas
        )

        def get_x_prev_and_pred_x0(e_t, index):
            # select parameters corresponding to the currently considered timestep
            a_t = torch.full((b, 1, 1, 1), alphas[index], device=device)
            a_prev = torch.full((b, 1, 1, 1), alphas_prev[index], device=device)
            sigma_t = torch.full((b, 1, 1, 1), sigmas[index], device=device)
            sqrt_one_minus_at = torch.full(
                (b, 1, 1, 1), sqrt_one_minus_alphas[index], device=device
            )

            # current prediction for x_0
            pred_x0 = (x - sqrt_one_minus_at * e_t) / a_t.sqrt()
            if quantize_denoised:
                pred_x0, _, *_ = self.model.first_stage_model.quantize(pred_x0)
            # direction pointing to x_t
            dir_xt = (1.0 - a_prev - sigma_t**2).sqrt() * e_t
            noise = sigma_t * noise_like(x.shape, device, repeat_noise) * temperature
            if noise_dropout > 0.0:
                noise = torch.nn.functional.dropout(noise, p=noise_dropout)
            x_prev = a_prev.sqrt() * pred_x0 + dir_xt + noise
            return x_prev, pred_x0

        e_t = get_model_output(x, t)
        if len(old_eps) == 0:
            # Pseudo Improved Euler (2nd order)
            x_prev, pred_x0 = get_x_prev_and_pred_x0(e_t, index)
            e_t_next = get_model_output(x_prev, t_next)
            e_t_prime = (e_t + e_t_next) / 2
        elif len(old_eps) == 1:
            # 2nd order Pseudo Linear Multistep (Adams-Bashforth)
            e_t_prime = (3 * e_t - old_eps[-1]) / 2
        elif len(old_eps) == 2:
            # 3nd order Pseudo Linear Multistep (Adams-Bashforth)
            e_t_prime = (23 * e_t - 16 * old_eps[-1] + 5 * old_eps[-2]) / 12
        elif len(old_eps) >= 3:
            # 4nd order Pseudo Linear Multistep (Adams-Bashforth)
            e_t_prime = (
                55 * e_t - 59 * old_eps[-1] + 37 * old_eps[-2] - 9 * old_eps[-3]
            ) / 24

        x_prev, pred_x0 = get_x_prev_and_pred_x0(e_t_prime, index)

        return x_prev, pred_x0, e_t
