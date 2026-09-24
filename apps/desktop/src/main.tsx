import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { useApp } from "./store";
import "./styles.css";

/** 언어를 바꾸면 화면 전체를 새로 그림 (문구는 그릴 때 t()로 번역함) */
function Root() {
  const lang = useApp((s) => s.lang);
  return <App key={lang} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
