import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const Intro: React.FC<{ title: string; subtitle: string }> = ({
  title,
  subtitle,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const titleScale = spring({ frame, fps, config: { damping: 12 } });
  const lineWidth = interpolate(frame, [15, 45], [0, 400], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const subtitleOpacity = interpolate(frame, [30, 50], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const subtitleY = interpolate(frame, [30, 50], [20, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 15, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill
      className="items-center justify-center bg-slate-900 text-white"
      style={{ opacity: fadeOut }}
    >
      <h1
        className="text-8xl font-bold"
        style={{ transform: `scale(${titleScale})` }}
      >
        {title}
      </h1>
      <div
        className="my-6 h-1 rounded bg-sky-400"
        style={{ width: lineWidth }}
      />
      <p
        className="text-3xl text-slate-300"
        style={{ opacity: subtitleOpacity, transform: `translateY(${subtitleY}px)` }}
      >
        {subtitle}
      </p>
    </AbsoluteFill>
  );
};
