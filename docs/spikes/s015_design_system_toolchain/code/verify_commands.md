# s015 复现命令

环境：Node 26.13.0，精确固定版本：

```bash
npm init -y
npm install --save-exact @google/design.md@0.4.0 @tailwindcss/vite@4.3.4 tailwindcss@4.3.4 vite@8.3.5
npx @google/design.md lint DESIGN_SPIKE.md   # 期望 {"errors":0,"warnings":0,"infos":1}
node --input-type=module -e "import {lint} from '@google/design.md/linter'; import {readFileSync} from 'node:fs'; const r=lint(readFileSync('DESIGN_SPIKE.md','utf8')); console.log(r.summary, r.designSystem.colors instanceof Map, r.designSystem.colors.get('light-accent')?.hex); npx vite build --config vite.config.mjs
```
