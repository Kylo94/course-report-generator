/**
 * 系统设置组件
 * 允许用户修改运行时配置（默认项目目录、输出目录、图片转换参数等）
 */
const SettingsView = {
  template: `
    <div>
      <h2 style="margin-bottom: 20px;">⚙️ 系统设置</h2>

      <el-alert
        title="设置即时生效，自动保存，无需重启"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 20px;"
      />

      <el-card class="section-card" style="margin-bottom:16px;">
        <template #header>
          <div style="display:flex;align-items:center;gap:6px;">
            <el-icon size="16"><FolderOpened /></el-icon>
            <span>默认路径</span>
          </div>
        </template>
        <el-form label-width="140px" size="small">
          <el-form-item label="默认项目目录">
            <div style="display:flex;gap:8px;width:100%;">
              <el-input v-model="form.default_project_dir" placeholder="留空则由前端从桌面/文稿起始" readonly>
                <template #append>
                  <el-button @click="openDirBrowser('project')">浏览</el-button>
                </template>
              </el-input>
              <el-button v-if="form.default_project_dir" type="danger" plain size="small" @click="form.default_project_dir = ''">
                清空
              </el-button>
            </div>
          </el-form-item>
          <el-form-item label="默认输出目录">
            <div style="display:flex;gap:8px;width:100%;">
              <el-input v-model="form.custom_output_dir" placeholder="留空则使用内置 data/reports" readonly>
                <template #append>
                  <el-button @click="openDirBrowser('output')">浏览</el-button>
                </template>
              </el-input>
              <el-button v-if="form.custom_output_dir" type="danger" plain size="small" @click="form.custom_output_dir = ''">
                清空
              </el-button>
            </div>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="section-card" style="margin-bottom:16px;">
        <template #header>
          <div style="display:flex;align-items:center;gap:6px;">
            <el-icon size="16"><Picture /></el-icon>
            <span>PDF 转图片</span>
          </div>
        </template>
        <el-form label-width="140px" size="small">
          <el-form-item label="启用转换">
            <el-switch v-model="form.image_enabled" />
            <span style="margin-left:8px;color:#909399;font-size:12px;">
              导出 PDF 后自动生成长图 JPG
            </span>
          </el-form-item>
          <el-form-item label="图片 DPI">
            <div style="display:flex;gap:12px;align-items:center;width:100%;">
              <el-slider v-model="form.image_dpi" :min="72" :max="300" :step="1" style="flex:1;" />
              <span style="min-width:50px;">{{ form.image_dpi }} DPI</span>
            </div>
            <p style="margin:4px 0 0;color:#909399;font-size:12px;">
              越高越清晰，但文件越大。默认 150，建议范围 100-200
            </p>
          </el-form-item>
          <el-form-item label="JPEG 质量">
            <div style="display:flex;gap:12px;align-items:center;width:100%;">
              <el-slider v-model="form.image_quality" :min="50" :max="100" :step="1" style="flex:1;" />
              <span style="min-width:50px;">{{ form.image_quality }}%</span>
            </div>
            <p style="margin:4px 0 0;color:#909399;font-size:12px;">
              越高画质越好，文件越大。默认 95
            </p>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="section-card" style="margin-bottom:16px;">
        <template #header>
          <div style="display:flex;align-items:center;gap:6px;">
            <el-icon size="16"><Clock /></el-icon>
            <span>编辑器</span>
          </div>
        </template>
        <el-form label-width="140px" size="small">
          <el-form-item label="自动保存间隔">
            <div style="display:flex;gap:12px;align-items:center;width:100%;">
              <el-slider v-model="form.auto_save_interval_seconds" :min="10" :max="120" :step="5" style="flex:1;" />
              <span style="min-width:50px;">{{ form.auto_save_interval_seconds }}秒</span>
            </div>
          </el-form-item>
        </el-form>
      </el-card>

      <div style="text-align:center;margin-top:20px;">
        <el-button type="primary" @click="saveSettings" :loading="saving">
          保存设置
        </el-button>
        <el-button @click="resetToDefaults">恢复默认</el-button>
      </div>

      <!-- ======================== 目录浏览器弹窗 ======================== -->
      <el-dialog v-model="dirBrowserVisible" title="选择目录" width="500px"
        :close-on-click-modal="false">
        <div>
          <div style="margin-bottom:10px;color:#606266;">
            当前路径：<code style="font-size:13px;">{{ dirBrowserPath || '(根目录)' }}</code>
          </div>
          <div v-if="dirBrowserLoading" style="text-align:center;padding:20px;">
            <el-icon class="is-loading" :size="20"><Loading /></el-icon>
            <span style="margin-left:8px;">加载中...</span>
          </div>
          <div v-else-if="dirBrowserError" style="color:#f56c6c;padding:10px;">{{ dirBrowserError }}</div>
          <el-scrollbar v-else max-height="300px">
            <div v-for="item in dirBrowserItems" :key="item.path"
              :class="{ 'dir-item': true, 'dir-item-parent': item.is_parent }"
              @click="browseDir(item.path)">
              <span>{{ item.name }}</span>
            </div>
            <div v-if="dirBrowserItems.length === 0" style="text-align:center;padding:20px;color:#909399;">
              空目录
            </div>
          </el-scrollbar>
        </div>
        <template #footer>
          <el-button @click="dirBrowserVisible = false">取消</el-button>
          <el-button type="primary" :disabled="!dirBrowserPath" @click="confirmDirBrowser">
            选择此目录
          </el-button>
        </template>
      </el-dialog>
    </div>
  `,

  data() {
    return {
      form: {
        default_project_dir: '',
        custom_output_dir: '',
        image_dpi: 150,
        image_quality: 95,
        image_enabled: true,
        auto_save_interval_seconds: 30,
      },
      saving: false,
      defaults: null, // 保存初始值，用于恢复默认

      // 目录浏览器
      dirBrowserMode: 'project',
      dirBrowserVisible: false,
      dirBrowserPath: '',
      dirBrowserItems: [],
      dirBrowserLoading: false,
      dirBrowserError: null,
    };
  },

  async mounted() {
    this.Router = Router;
    await this.loadSettings();
  },

  methods: {
    async loadSettings() {
      try {
        const data = await API.settings.get();
        this.form = { ...this.form, ...data };
        // 保存一份默认值快照
        if (!this.defaults) {
          this.defaults = { ...data };
        }
      } catch (e) {
        this.$message.error('加载设置失败: ' + e.message);
      }
    },

    async saveSettings() {
      this.saving = true;
      try {
        const result = await API.settings.save(this.form);
        this.form = { ...this.form, ...result };
        this.$message.success('设置已保存');
      } catch (e) {
        this.$message.error('保存设置失败: ' + e.message);
      } finally {
        this.saving = false;
      }
    },

    resetToDefaults() {
      if (!this.form.image_dpi) return;
      this.form = {
        default_project_dir: '',
        custom_output_dir: '',
        image_dpi: 150,
        image_quality: 95,
        image_enabled: true,
        auto_save_interval_seconds: 30,
      };
      this.saveSettings();
    },

    // ======================== 目录浏览器 ========================
    openDirBrowser(mode) {
      this.dirBrowserMode = mode;
      this.dirBrowserPath = mode === 'project' ? this.form.default_project_dir : this.form.custom_output_dir;
      this.dirBrowserItems = [];
      this.dirBrowserError = null;
      this.dirBrowserVisible = true;
      this.browseToDir(this.dirBrowserPath || '');
    },

    async browseToDir(path) {
      this.dirBrowserLoading = true;
      this.dirBrowserError = null;
      try {
        const result = await API.projects.listDir({ path });
        if (result.error) {
          this.dirBrowserError = result.error;
          return;
        }
        this.dirBrowserPath = result.path;
        this.dirBrowserItems = result.items;
      } catch (e) {
        this.dirBrowserError = '加载失败: ' + e.message;
      } finally {
        this.dirBrowserLoading = false;
      }
    },

    browseDir(path) {
      this.browseToDir(path);
    },

    confirmDirBrowser() {
      if (!this.dirBrowserPath) return;
      if (this.dirBrowserMode === 'project') {
        this.form.default_project_dir = this.dirBrowserPath;
      } else {
        this.form.custom_output_dir = this.dirBrowserPath;
      }
      this.dirBrowserVisible = false;
    },
  },
};
