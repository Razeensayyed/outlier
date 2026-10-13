"use client"

import { useCallback, useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import { Dumbbell, Flame, Zap } from "lucide-react"
import AnimatedPathText from "@/components/ui/text-along-path"
import { Button } from "@/components/ui/button"

const rectPath =
  "M 20,20 L 180,20 A 20,20 0 0,1 200,40 L 200,160 A 20,20 0 0,1 180,180 L 20,180 A 20,20 0 0,1 0,160 L 0,40 A 20,20 0 0,1 20,20"

const buttonCopy = {
  idle: "Join Waitlist",
  loading: (
    <motion.div className="h-3 w-3 sm:h-4 sm:w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
  ),
  success: "You're in ✓",
} as const

export default function WaitlistForm() {
  const [buttonState, setButtonState] = useState<"idle" | "loading" | "success">("idle")
  const [email, setEmail] = useState("")
  const [count] = useState(247)

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      if (buttonState === "success" || !email) return

      setButtonState("loading")
      setTimeout(() => setButtonState("success"), 1750)
      setTimeout(() => {
        setButtonState("idle")
        setEmail("")
      }, 3500)
    },
    [buttonState, email],
  )

  return (
    <div className="w-dvw min-h-dvh flex flex-col justify-center items-center text-[#0015ff] relative bg-white overflow-hidden">
      {/* Animated border text */}
      <AnimatedPathText
        path={rectPath}
        svgClassName="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 py-2 sm:py-8 w-[min(90vw,480px)] h-[min(90vw,480px)]"
        viewBox="-20 10 240 180"
        text="KUNAL FITNESS ✦ JOIN THE WAITLIST ✉ KUNAL FITNESS ✦ JOIN THE WAITLIST ✉ "
        textClassName="text-[10.6px] font-mono text-[#0015ff] opacity-60"
        duration={22}
        preserveAspectRatio="none"
        textAnchor="start"
      />

      {/* Card */}
      <div className="relative z-10 w-[min(90vw,340px)] sm:w-80 bg-white/90 backdrop-blur-sm border border-[#0015ff]/20 rounded-2xl shadow-xl p-8">
        {/* Logo / icon */}
        <div className="flex justify-center mb-6">
          <div className="h-14 w-14 rounded-full bg-[#0015ff] flex items-center justify-center shadow-lg">
            <Dumbbell className="h-7 w-7 text-white" />
          </div>
        </div>

        {/* Headline */}
        <h1 className="text-center text-2xl sm:text-3xl font-extrabold tracking-tight text-[#0015ff] mb-1">
          Kunal Fitness
        </h1>
        <p className="text-center text-xs sm:text-sm text-[#0015ff]/60 mb-6 font-mono">
          Train smarter. Live stronger.
        </p>

        {/* Features */}
        <ul className="space-y-2 mb-7">
          {[
            { icon: <Flame className="h-4 w-4" />, text: "Personalised workout plans" },
            { icon: <Zap className="h-4 w-4" />, text: "AI-powered progress tracking" },
            { icon: <Dumbbell className="h-4 w-4" />, text: "Expert nutrition guidance" },
          ].map(({ icon, text }) => (
            <li key={text} className="flex items-center gap-2 text-xs sm:text-sm text-[#0015ff]/80 font-mono">
              <span className="shrink-0">{icon}</span>
              {text}
            </li>
          ))}
        </ul>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="email"
            required
            placeholder="your@email.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-2.5 border border-[#0015ff]/40 focus:outline-none focus:ring-2 focus:ring-[#0015ff]/30 font-mono text-xs sm:text-sm placeholder:text-[#0015ff]/40 rounded-lg bg-white text-[#0015ff]"
          />
          <Button
            type="submit"
            disabled={buttonState === "loading"}
            className="w-full h-10 sm:h-11 bg-[#0015ff] text-white hover:bg-[#0015ff]/90 transition-colors font-mono text-xs sm:text-sm rounded-lg"
          >
            <AnimatePresence mode="popLayout" initial={false}>
              <motion.span
                key={buttonState}
                transition={{ type: "spring", duration: 0.3, bounce: 0 }}
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
              >
                {buttonCopy[buttonState]}
              </motion.span>
            </AnimatePresence>
          </Button>
        </form>

        {/* Social proof */}
        <p className="mt-4 text-center text-[10px] sm:text-xs text-[#0015ff]/50 font-mono">
          {count}+ people already on the list
        </p>
      </div>
    </div>
  )
}
