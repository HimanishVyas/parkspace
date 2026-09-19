import { useTheme } from "../lib/theme";

/**
 * One button that flips between light and dark. A three-way control would be
 * more precise, but the common need is simply "this is too dark right now",
 * and the device default still applies until someone touches it.
 */
export default function ThemeToggle({ className = "" }: { className?: string }) {
  const { resolved, toggle } = useTheme();
  const goingTo = resolved === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className={`theme-toggle ${className}`.trim()}
      onClick={toggle}
      aria-label={`Switch to ${goingTo} mode`}
      title={`Switch to ${goingTo} mode`}
    >
      <span aria-hidden="true">{resolved === "dark" ? "☀" : "☾"}</span>
    </button>
  );
}
