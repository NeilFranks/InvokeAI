import { useHotkeys } from 'react-hotkeys-hook';
import { FaPlay } from 'react-icons/fa';
import { readinessSelector } from 'app/selectors/readinessSelector';
import { stream } from 'app/socketio/actions';
import { useAppDispatch, useAppSelector } from 'app/store';
import IAIButton, { IAIButtonProps } from 'common/components/IAIButton';
import IAIIconButton, {
  IAIIconButtonProps,
} from 'common/components/IAIIconButton';
import { activeTabNameSelector } from 'features/options/store/optionsSelectors';

interface StreamButton
  extends Omit<IAIButtonProps | IAIIconButtonProps, 'aria-label'> {
  iconButton?: boolean;
}

export default function StreamButton(props: StreamButton) {
  const { iconButton = false, ...rest } = props;
  const dispatch = useAppDispatch();
  const { isReady } = useAppSelector(readinessSelector);
  const activeTabName = useAppSelector(activeTabNameSelector);

  const handleClickGenerate = () => {
    dispatch(stream(activeTabName));
  };

  useHotkeys(
    ['ctrl+enter', 'meta+enter'],
    () => {
      dispatch(stream(activeTabName));
    },
    {
      enabled: () => isReady,
      preventDefault: true,
      enableOnFormTags: ['input', 'textarea', 'select'],
    },
    [isReady, activeTabName]
  );

  return (
    <div style={{ flexGrow: 4 }}>
      {iconButton ? (
        <IAIIconButton
          aria-label="Stream"
          type="submit"
          icon={<FaPlay />}
          isDisabled={!isReady}
          onClick={handleClickGenerate}
          className="invoke-btn"
          tooltip="Stream"
          tooltipProps={{ placement: 'bottom' }}
          {...rest}
        />
      ) : (
        <IAIButton
          aria-label="Stream"
          type="submit"
          isDisabled={!isReady}
          onClick={handleClickGenerate}
          className="invoke-btn"
          {...rest}
        >
          Stream
        </IAIButton>
      )}
    </div>
  );
}
