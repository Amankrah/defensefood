"use client";

import { BlockMath } from "react-katex";
import "katex/dist/katex.min.css";

interface FormulaBlockProps {
  latex: string;
}

/**
 * Render a LaTeX formula as a centred KaTeX block.
 *
 * Wrapped in a try/catch via the `errorColor` prop so a malformed string
 * shows up red instead of crashing the page.
 */
export default function FormulaBlock({ latex }: FormulaBlockProps) {
  return (
    <div className="overflow-x-auto rounded-lg bg-slate-50 px-3 py-2 text-slate-800">
      <BlockMath math={latex} errorColor="#ef4444" />
    </div>
  );
}
