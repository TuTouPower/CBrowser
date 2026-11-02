# p014 确认 v2 上传文件在容器文件选择器可达

- 来源：t008 review（storage_and_artifacts AC-003 改写）
- 内容：baseline spec 原 AC-003 要求上传文件在容器内 GTK 文件选择对话框中可选择；t008 交付了 `/exchange/uploads` 挂载、容器路径与 UI 管理，但没有验证或实现文件选择器书签/对话框集成。需确认该行为是否仍属 v2 范围：若需要，补文件选择器桥接与真实 Chrome 选择文件验收；若放弃，更新 spec 并记录用户决定。
- 处理：main；resolution=resolved；reason=Browser Runtime 镜像加 GTK 3（原先无 GTK/portal，页面文件输入点击无反应），入口写 GTK 书签 Uploads -> /exchange/uploads，Runtime Agent 注入 --disable-gtk-ime 防组合输入错字；test_p014_file_input_opens_chooser_with_uploads_bookmark 与 browser runtime 16 项、stream composition E2E 通过
