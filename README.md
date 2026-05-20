## Install
```
pip3 install -r requirements.txt
```

## Run Streamlit
```
streamlit run app.py
```

若是在远程服务器部署，本地可以通过 ssh 转发
```
ssh -L ${local_port}:127.0.0.1:${remote_port} name@ip
```

## Build Static Web Page
```
python3 build_web.py
```

执行后会生成 `docs/index.html`，可直接在本地用网页打开查看。

## GitHub Actions 部署网页
- 工作流文件：`.github/workflows/deploy-pages.yml`
- 触发方式：推送到 `main` 或 `master`，或手动触发
- 部署目标：GitHub Pages

首次使用请在仓库设置中开启 Pages（Source 选择 GitHub Actions）。