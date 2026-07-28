import * as Select from "@radix-ui/react-select";
import {
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
} from "react";

interface NativeOption {
  disabled: boolean;
  label: string;
  value: string;
}

interface SelectSnapshot {
  disabled: boolean;
  options: NativeOption[];
  signature: string;
  value: string;
}

interface AppSelectProps {
  ariaLabel: string;
  nativeSelect: HTMLSelectElement;
}

const SELECT_VALUE_PREFIX = "douk-select:";
const selectSyncSubscribers = new Set<() => void>();
let selectSyncTimer: number | undefined;

function encodeValue(value: string) {
  return `${SELECT_VALUE_PREFIX}${encodeURIComponent(value)}`;
}

function decodeValue(value: string) {
  return decodeURIComponent(value.slice(SELECT_VALUE_PREFIX.length));
}

function readSelect(nativeSelect: HTMLSelectElement): SelectSnapshot {
  const options = Array.from(nativeSelect.options).map((option) => ({
    disabled: option.disabled,
    label: option.label || option.textContent?.trim() || option.value,
    value: option.value,
  }));
  const signature = JSON.stringify({
    disabled: nativeSelect.disabled,
    options,
    value: nativeSelect.value,
  });

  return {
    disabled: nativeSelect.disabled,
    options,
    signature,
    value: nativeSelect.value,
  };
}

function subscribeToSelectSync(callback: () => void) {
  selectSyncSubscribers.add(callback);
  if (selectSyncTimer === undefined) {
    selectSyncTimer = window.setInterval(() => {
      selectSyncSubscribers.forEach((subscriber) => subscriber());
    }, 300);
  }

  return () => {
    selectSyncSubscribers.delete(callback);
    if (selectSyncSubscribers.size === 0 && selectSyncTimer !== undefined) {
      window.clearInterval(selectSyncTimer);
      selectSyncTimer = undefined;
    }
  };
}

function ChevronIcon({ direction }: { direction: "down" | "up" }) {
  return (
    <svg
      aria-hidden="true"
      className="app-select-chevron"
      fill="none"
      viewBox="0 0 24 24"
    >
      <path
        d={direction === "down" ? "m6 9 6 6 6-6" : "m18 15-6-6-6 6"}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      className="app-select-check"
      fill="none"
      viewBox="0 0 24 24"
    >
      <path
        d="m5 12 4 4L19 6"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function AppSelect({ ariaLabel, nativeSelect }: AppSelectProps) {
  const [snapshot, setSnapshot] = useState(() => readSelect(nativeSelect));

  const syncFromNative = useCallback(() => {
    const nextSnapshot = readSelect(nativeSelect);
    setSnapshot((current) =>
      current.signature === nextSnapshot.signature ? current : nextSnapshot,
    );
  }, [nativeSelect]);

  useEffect(() => {
    const observer = new MutationObserver(syncFromNative);
    const handleNativeChange = () => syncFromNative();

    observer.observe(nativeSelect, {
      attributes: true,
      childList: true,
      subtree: true,
    });
    nativeSelect.addEventListener("change", handleNativeChange);
    nativeSelect.addEventListener("input", handleNativeChange);
    const unsubscribe = subscribeToSelectSync(syncFromNative);

    return () => {
      observer.disconnect();
      nativeSelect.removeEventListener("change", handleNativeChange);
      nativeSelect.removeEventListener("input", handleNativeChange);
      unsubscribe();
    };
  }, [nativeSelect, syncFromNative]);

  const updateNativeValue = (encodedValue: string) => {
    nativeSelect.value = decodeValue(encodedValue);
    nativeSelect.dispatchEvent(new Event("input", { bubbles: true }));
    nativeSelect.dispatchEvent(new Event("change", { bubbles: true }));
    syncFromNative();
  };

  const contentStyle = {
    "--app-select-trigger-width": "var(--radix-select-trigger-width)",
  } as CSSProperties;

  return (
    <Select.Root
      disabled={snapshot.disabled}
      value={encodeValue(snapshot.value)}
      onOpenChange={(open) => {
        if (open) {
          syncFromNative();
        }
      }}
      onValueChange={updateNativeValue}
    >
      <Select.Trigger
        aria-label={ariaLabel}
        className="app-select-trigger"
        data-native-select={nativeSelect.id || nativeSelect.name}
      >
        <Select.Value />
        <Select.Icon className="app-select-trigger-icon">
          <ChevronIcon direction="down" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          className="app-select-content"
          collisionPadding={12}
          position="popper"
          sideOffset={6}
          style={contentStyle}
        >
          <Select.ScrollUpButton className="app-select-scroll-button">
            <ChevronIcon direction="up" />
          </Select.ScrollUpButton>
          <Select.Viewport className="app-select-viewport">
            {snapshot.options.map((option, index) => (
              <Select.Item
                className="app-select-item"
                disabled={option.disabled}
                key={`${option.value}:${index}`}
                value={encodeValue(option.value)}
              >
                <Select.ItemText>{option.label}</Select.ItemText>
                <Select.ItemIndicator className="app-select-indicator">
                  <CheckIcon />
                </Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
          <Select.ScrollDownButton className="app-select-scroll-button">
            <ChevronIcon direction="down" />
          </Select.ScrollDownButton>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
