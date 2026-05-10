/** Shared Framer Motion animation variants (Minimalist Modern design system). */

export const easeOut = [0.16, 1, 0.3, 1] as const;

// ── Entrance ──
export const fadeInUp = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.7, ease: easeOut } },
};

export const fadeIn = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.7, ease: easeOut } },
};

export const fadeInLeft = {
  hidden: { opacity: 0, x: -24 },
  visible: { opacity: 1, x: 0, transition: { duration: 0.6, ease: easeOut } },
};

export const fadeInRight = {
  hidden: { opacity: 0, x: 24 },
  visible: { opacity: 1, x: 0, transition: { duration: 0.6, ease: easeOut } },
};

export const scaleIn = {
  hidden: { opacity: 0, scale: 0.95 },
  visible: { opacity: 1, scale: 1, transition: { duration: 0.5, ease: easeOut } },
};

// ── Stagger containers ──
export const stagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } },
};

export const staggerSlow = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.12, delayChildren: 0.1 } },
};

// ── Continuous ──
export const float = {
  animate: {
    y: [0, -10, 0],
    transition: { duration: 5, ease: "easeInOut", repeat: Infinity },
  },
};

export const pulse = {
  animate: {
    scale: [1, 1.05, 1],
    opacity: [1, 0.85, 1],
    transition: { duration: 2, ease: "easeInOut", repeat: Infinity },
  },
};

// ── Motion props helpers ──
export const viewportOnce = {
  once: true,
  amount: 0.15,
  margin: "-60px",
} as const;
