"use client";

import { motion, useReducedMotion } from "framer-motion";

type SectionTitleProps = {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  className?: string;
  align?: "left" | "center";
};

export function SectionTitle({
  eyebrow,
  title,
  subtitle,
  className = "",
  align = "left",
}: SectionTitleProps) {
  const reducedMotion = useReducedMotion();
  const alignment = align === "center" ? "text-center items-center" : "text-left items-start";

  return (
    <motion.div
      className={`mb-8 flex flex-col gap-3 ${alignment} ${className}`}
      initial={reducedMotion ? false : { opacity: 0, y: 14 }}
      whileInView={reducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.35 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      {eyebrow ? (
        <span className="font-display text-xs uppercase tracking-[0.24em] text-accent/85">
          {eyebrow}
        </span>
      ) : null}

      <h2
        className="glitch-title glitch-active font-display text-2xl font-bold tracking-tight text-foreground sm:text-3xl"
        data-text={title}
      >
        {title}
      </h2>

      {subtitle ? <p className="max-w-3xl text-sm text-white/75 sm:text-base">{subtitle}</p> : null}
    </motion.div>
  );
}
