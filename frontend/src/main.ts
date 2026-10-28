import "./styles/fonts.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components/buttons.css";
import "./styles/components/forms.css";
import "./styles/components/feedback.css";
import "./styles/components/data.css";
import "htmx.org";
import { initToasts } from "./toast";

document.documentElement.classList.add("js");
initToasts();
