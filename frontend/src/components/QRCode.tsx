/**
 * Booking QR code, rendered as SVG.
 *
 * V1 encodes a digital identifier only ("PARKSPACE:PS-7F3K9Q") — it opens no
 * barrier, a guard scans it to look the booking up (PRD §19). Encoding is
 * delegated to `qrcode-generator` rather than hand-rolled: a subtly malformed
 * code that won't scan at the gate is exactly the failure a pilot can't debug.
 */
import qrcode from "qrcode-generator";

export default function QRCode({ value, size = 180 }: { value: string; size?: number }) {
  // Type 0 = pick the smallest version that fits; "M" tolerates a scuffed screen.
  const qr = qrcode(0, "M");
  qr.addData(value);
  qr.make();

  const count = qr.getModuleCount();
  const quiet = 4;
  const dimension = count + quiet * 2;
  const path: string[] = [];
  for (let row = 0; row < count; row++) {
    for (let col = 0; col < count; col++) {
      if (qr.isDark(row, col)) path.push(`M${col + quiet} ${row + quiet}h1v1h-1z`);
    }
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${dimension} ${dimension}`}
      role="img"
      aria-label={`QR code for ${value}`}
      shapeRendering="crispEdges"
    >
      <rect width={dimension} height={dimension} fill="#ffffff" />
      <path d={path.join("")} fill="#0f172a" />
    </svg>
  );
}
