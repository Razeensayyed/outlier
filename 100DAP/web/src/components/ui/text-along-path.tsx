import { RefObject, useEffect, useId, useRef } from "react"
import { useScroll, UseScrollOptions, useTransform } from "motion/react"

type PreserveAspectRatioAlign =
  | "none"
  | "xMinYMin"
  | "xMidYMin"
  | "xMaxYMin"
  | "xMinYMid"
  | "xMidYMid"
  | "xMaxYMid"
  | "xMinYMax"
  | "xMidYMax"
  | "xMaxYMax"

type PreserveAspectRatioMeetOrSlice = "meet" | "slice"

type PreserveAspectRatio =
  | PreserveAspectRatioAlign
  | `${Exclude<PreserveAspectRatioAlign, "none">} ${PreserveAspectRatioMeetOrSlice}`

interface AnimatedPathTextProps {
  path: string
  pathId?: string
  pathClassName?: string
  preserveAspectRatio?: PreserveAspectRatio
  showPath?: boolean

  width?: string | number
  height?: string | number
  viewBox?: string
  svgClassName?: string

  text: string
  textClassName?: string
  textAnchor?: "start" | "middle" | "end"

  animationType?: "auto" | "scroll"

  duration?: number
  repeatCount?: number | "indefinite"
  easingFunction?: {
    calcMode?: string
    keyTimes?: string
    keySplines?: string
  }

  scrollContainer?: RefObject<HTMLElement | null>
  scrollOffset?: UseScrollOptions["offset"]
  scrollTransformValues?: [number, number]
}

const AnimatedPathText = ({
  path,
  pathId,
  pathClassName,
  preserveAspectRatio = "xMidYMid meet",
  showPath = false,

  width = "100%",
  height = "100%",
  viewBox = "0 0 100 100",
  svgClassName,

  text,
  textClassName,
  textAnchor = "start",

  animationType = "auto",

  duration = 4,
  repeatCount = "indefinite",

  easingFunction = {},

  scrollContainer,
  scrollOffset = ["start end", "end end"],
  scrollTransformValues = [0, 100],
}: AnimatedPathTextProps) => {
  const textPathRefs = useRef<SVGTextPathElement[]>([])
  const generatedId = useId()
  const id = pathId || `animated-path-${generatedId.replace(/:/g, "")}`

  const { scrollYProgress } = useScroll({
    ...(scrollContainer && { container: scrollContainer }),
    offset: scrollOffset,
  })

  const t = useTransform(scrollYProgress, [0, 1], scrollTransformValues)

  useEffect(() => {
    const handleChange = () => {
      textPathRefs.current.forEach((textPath) => {
        if (textPath) {
          textPath.setAttribute("startOffset", `${t.get()}%`)
        }
      })
    }

    scrollYProgress.on("change", handleChange)

    return () => {
      scrollYProgress.clearListeners()
    }
  }, [scrollYProgress, t])

  const animationProps =
    animationType === "auto"
      ? {
          from: "0%",
          to: "100%",
          begin: "0s",
          dur: `${duration}s`,
          repeatCount: repeatCount,
          ...(easingFunction && easingFunction),
        }
      : null

  return (
    <svg
      className={svgClassName}
      xmlns="http://www.w3.org/2000/svg"
      width={width}
      height={height}
      viewBox={viewBox}
      preserveAspectRatio={preserveAspectRatio}
    >
      <path
        id={id}
        className={pathClassName}
        d={path}
        stroke={showPath ? "currentColor" : "none"}
        fill="none"
      />

      <text textAnchor={textAnchor} fill="currentColor">
        <textPath
          className={textClassName}
          href={`#${id}`}
          startOffset={"0%"}
          ref={(ref) => {
            if (ref) textPathRefs.current[0] = ref
          }}
        >
          {animationType === "auto" && (
            <animate attributeName="startOffset" {...animationProps} />
          )}
          {text}
        </textPath>
      </text>

      {animationType === "auto" && (
        <text textAnchor={textAnchor} fill="currentColor">
          <textPath
            className={textClassName}
            href={`#${id}`}
            startOffset={"-100%"}
            ref={(ref) => {
              if (ref) textPathRefs.current[1] = ref
            }}
          >
            {animationType === "auto" && (
              <animate
                attributeName="startOffset"
                {...animationProps}
                from="-100%"
                to="0%"
              />
            )}
            {text}
          </textPath>
        </text>
      )}
    </svg>
  )
}

export default AnimatedPathText
