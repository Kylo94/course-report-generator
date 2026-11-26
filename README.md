# GitHub Pages 站点源码

这个分支是 `course-report-generator` 的项目主页源码，独立于 `main` 分支，避免站点文件混入项目代码。

## 更新方式

```bash
git clone -b gh-pages git@github.com:Kylo94/course-report-generator.git
cd course-report-generator
# 修改 index.html / styles.css / script.js
git add .
git commit -m "docs: 更新项目主页"
git push origin gh-pages
```

GitHub Pages 发布：仓库 Settings → Pages → Source 选择 `Deploy from a branch`，分支选 `gh-pages`，目录选 `/ (root)`。

站点地址通常为：`https://kylo94.github.io/course-report-generator/`
