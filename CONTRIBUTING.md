# 参与贡献

感谢你改进“换影”。提交代码前，请先在 Issue 中说明要解决的问题；小型修复可以直接提交 Pull Request。

## 本地开发

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python download_model.py
.venv/bin/python server.py
```

运行无需付费接口的测试：

```bash
.venv/bin/python -m unittest -v
```

`live_smoke_test.py` 会调用真实图片服务并产生费用，除非你明确需要端到端验证，否则不要运行。

## Pull Request 要求

- 不得提交 `.env`、API 密钥、真人私密图片、模型权重或 `outputs/` 中的结果。
- 为行为变更增加或更新测试。
- 涉及上传、网络访问、文件读取或令牌处理的改动，需要说明安全影响。
- 提交即表示你有权贡献相关代码和素材，并同意贡献按 Apache-2.0 许可证发布。
