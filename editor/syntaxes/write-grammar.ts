/** `npm run grammar`: write the `.script` grammar from its source. */

import { writeFileSync } from "node:fs";
import { join } from "node:path";

import { grammar, serialise } from "./scenet-script.grammar";

writeFileSync(join(__dirname, "scenet-script.tmLanguage.json"), serialise(grammar), "utf8");
