# p007 前端残留硬编码文案

- 来源：t007 评审遗留（t007_code_f004 修复后 Round 2 残留）
- 内容：会话、页头与 Profile 主表单已走 `t()`；`SettingsPage.tsx`、`ProfileNewPage.tsx` 部分标签/placeholder、`ProfileDetailPage.tsx` 个别 placeholder 及 `useBrowserSession.ts` 阶段错误详情仍为硬编码中/英文。设置页与文件页由 t008 改造，宜在 t008/t011 一并收口并补英文 locale 渲染测试。
- 处理：d7aeb01；resolution=resolved；reason=A29 补齐 SettingsPage、ProfileNewPage、ProfileDetailPage、useBrowserSession 的 t() 文案与中英字典，并新增语言切换断言测试
