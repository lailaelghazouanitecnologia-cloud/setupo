import "./index.css";
import "@radix-ui/themes/styles.css";
import { Theme } from "@radix-ui/themes";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <Theme appearance="dark" accentColor="violet" radius="medium" scaling="95%">
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </Theme>
);
