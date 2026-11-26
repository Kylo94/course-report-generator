const SITE_CONFIG = {
  version: "1.4.1",
  repo: "Kylo94/course-report-generator",
  assets: [
    {
      id: "windows-x64",
      platform: "Windows",
      arch: "x64",
      format: "ZIP",
      ext: "zip",
      icon: "windows",
      desc: "适合 64 位 Windows 10 / 11。",
      detail: "课程报告生成工具.exe + browser/",
    },
    {
      id: "macos-x64",
      platform: "macOS",
      arch: "Intel x64",
      format: "DMG",
      ext: "dmg",
      icon: "mac",
      desc: "适合 Intel 芯片的 Mac。",
      detail: "课程报告生成工具.app",
    },
    {
      id: "macos-arm64",
      platform: "macOS",
      arch: "Apple Silicon",
      format: "DMG",
      ext: "dmg",
      icon: "mac",
      desc: "适合 M1 / M2 / M3 及更新机型。",
      detail: "课程报告生成工具.app",
    },
    {
      id: "linux-x64",
      platform: "Linux",
      arch: "x64",
      format: "TAR.GZ",
      ext: "tar.gz",
      icon: "linux",
      desc: "适合 64 位 Linux 桌面发行版。",
      detail: "可执行文件 + browser/",
    },
  ],
};

const ICONS = {
  windows: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="8" height="8" rx="1"/><rect x="13" y="4" width="8" height="8" rx="1"/><rect x="3" y="14" width="8" height="8" rx="1"/><rect x="13" y="14" width="8" height="8" rx="1"/></svg>',
  mac: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M2 20h20M9 21h6"/></svg>',
  linux: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 10 3 2-3 2M12 15h5"/></svg>',
};

function detectRecommended() {
  const ua = navigator.userAgent;
  if (/Win/i.test(ua)) return "windows-x64";
  if (/Linux/i.test(ua) && !/Mac/i.test(ua)) return "linux-x64";
  return null;
}

function assetUrl(asset) {
  const file = `course-report-generator-${asset.id}-v${SITE_CONFIG.version}.${asset.ext}`;
  return `https://github.com/${SITE_CONFIG.repo}/releases/download/v${SITE_CONFIG.version}/${file}`;
}

function renderDownloads() {
  document.querySelectorAll("[data-version-label]").forEach((el) => {
    el.textContent = `v${SITE_CONFIG.version}`;
  });

  const grid = document.getElementById("download-grid");
  if (!grid) return;

  const recommended = detectRecommended();
  grid.innerHTML = SITE_CONFIG.assets
    .map((asset) => {
      const highlight = asset.id === recommended;
      return `
        <article class="download-card${highlight ? " is-recommended" : ""}">
          <div class="download-card-head">
            <span class="download-icon">${ICONS[asset.icon]}</span>
            <div>
              <span class="download-platform">${asset.platform}</span>
              <h3>${asset.arch}</h3>
            </div>
            ${highlight ? '<span class="recommended">当前系统</span>' : ""}
          </div>
          <p>${asset.desc}</p>
          <div class="download-file">${asset.detail}</div>
          <a class="download-btn" href="${assetUrl(asset)}" target="_blank" rel="noopener">
            下载 ${asset.format} <span aria-hidden="true">→</span>
          </a>
        </article>`;
    })
    .join("");
}

renderDownloads();

document.querySelectorAll(".copy").forEach((button) => {
  button.addEventListener("click", async () => {
    const block = button.closest(".code-block");
    const code = block && block.querySelector("code");
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code.textContent.trim());
      button.textContent = "已复制";
      button.classList.add("done");
      setTimeout(() => {
        button.textContent = "复制";
        button.classList.remove("done");
      }, 1600);
    } catch (error) {
      button.textContent = "复制失败";
      setTimeout(() => {
        button.textContent = "复制";
      }, 1600);
    }
  });
});
