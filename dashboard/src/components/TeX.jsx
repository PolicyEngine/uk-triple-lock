import katex from "katex";

/** Inline (or display) TeX, rendered to HTML at build and render time by KaTeX. */
export default function TeX({ tex, display = false }) {
  const html = katex.renderToString(tex, { displayMode: display, throwOnError: true, output: "html" });
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}
