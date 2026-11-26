/**
 * 系统设置组件
 * 允许用户修改运行时配置（AI 服务、默认模板、项目目录、图片转换参数等）
 */
const SettingsView = {
  template: `
    <div>
      <h2 style="margin-bottom: 20px;">⚙️ 系统设置</h2>

      <el-alert
        title="设置即时生效，无需重启；修改后点击底部「保存设置」"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 20px;"
      />

      <el-card class="section-card" style="margin-bottom:16px;">
        <template #header>
          <div style="display:flex;align-items:center;gap:6px;">
            <el-icon size="16"><Cpu /></el-icon>
            <span>AI 服务</span>
            <el-tag v-if="form.api_key_configured" type="success" size="small" style="margin-left:8px;">
              已配置 {{ form.api_key_hint }}
            </el-tag>
            <el-tag v-else type="warning" size="small" style="margin-left:8px;">未配置 API Key</el-tag>
          </div>
        </template>
        <el-form label-width="140px" size="small">
          <el-form-item label="供应商">
            <el-select v-model="form.llm_provider" style="width:240px;" @change="onProviderChange">
              <el-option v-for="p in providers" :key="p" :label="providerLabels[p] || p" :value="p" />
            </el-select>
          </el-form-item>
          <el-form-item label="API Key">
            <div style="width:100%;">
              <el-input v-model="form.llm_api_key" :type="showApiKey ? 'text' : 'password'"
                placeholder="留空表示保持当前配置不变" clearable>
                <template #suffix>
                  <el-button link size="small" @click="showApiKey = !showApiKey">
                    {{ showApiKey ? '隐藏' : '显示' }}
                  </el-button>
                </template>
              </el-input>
              <div style="margin-top:4px;color:#909399;font-size:12px;">
                Key 加密保存在系统钥匙串或本地加密文件中，不会明文写入配置文件。
                <el-button v-if="form.api_key_configured" link type="danger" size="small" @click="clearApiKey">
                  清除已保存的 Key
                </el-button>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="模型">
            <el-input v-model="form.llm_default_model" placeholder="例如 deepseek-chat" style="width:320px;" />
          </el-form-item>
          <el-form-item label="自定义 Base URL">
            <el-input v-model="form.llm_base_url" placeholder="留空则使用该供应商默认地址" style="width:420px;" />
          </el-form-item>
          <el-form-item label="超时（秒）">
            <el-input-number v-model="form.llm_timeout" :min="1" :max="600" controls-position="right" />
          </el-form-item>
          <el-form-item label="失败重试">
            <el-input-number v-model="form.llm_max_retries" :min="0" :max="10" controls-position="right" />
          </el-form-item>
          <el-form-item label="最大 Token">
            <el-input-number v-model="form.llm_max_tokens" :min="1" :max="1000000" :step="1024" controls-position="right" />
          </el-form-item>
          <el-form-item label="思考模式">
            <el-switch v-model="form.llm_thinking_enabled" />
            <span style="margin-left:8px;color:#909399;font-size:12px;">
              仅 DeepSeek 生效。开启后模型先推理再回答，成本约高 3 倍且更慢；默认关闭。
            </span>
          </el-form-item>
          <el-form-item>
            <el-collapse style="width:100%;">
              <el-collapse-item title="高级：各生成步骤的温度参数">
                <div style="display:flex;flex-wrap:wrap;gap:12px;">
                  <div v-for="(label, key) in temperatureLabels" :key="key" style="width:220px;">
                    <div style="font-size:12px;color:#606266;margin-bottom:4px;">{{ label }}</div>
                    <el-input-number v-model="form.llm_temperature[key]" :min="0" :max="2" :step="0.1"
                      :precision="1" controls-position="right" style="width:100%;" />
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </el-form-item>
          <el-form-item>
            <el-button :loading="testing" @click="saveAndTest">保存并测试连接</el-button>
            <span style="margin-left:8px;color:#909399;font-size:12px;">测试会先保存当前设置</span>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="section-card" style="margin-bottom:16px;">
        <template #header>
          <div style="display:flex;align-items:center;gap:6px;">
            <el-icon size="16"><Collection /></el-icon>
            <span>报告</span>
          </div>
        </template>
        <el-form label-width="140px" size="small">
          <el-form-item label="默认模板">
            <el-select v-model="form.default_template_id" style="width:320px;" placeholder="选择默认报告模板">
              <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
            <span style="margin-left:8px;color:#909399;font-size:12px;">批量生成时默认选中；也可在模板管理页设为默认</span>
          </el-form-item>
        </el-form>
      </el-card>

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
        default_template_id: 'classic',
        image_dpi: 150,
        image_quality: 95,
        image_enabled: true,
        auto_save_interval_seconds: 30,
        llm_provider: 'deepseek',
        llm_api_key: '',
        llm_base_url: '',
        llm_default_model: 'deepseek-chat',
        llm_max_tokens: 8192,
        llm_timeout: 60,
        llm_max_retries: 2,
        llm_thinking_enabled: false,
        llm_temperature: {
          knowledge_points: 0.3,
          content_summary: 0.5,
          homework: 0.5,
          vocabulary: 0.5,
          ability_improvement: 0.5,
          evaluation: 0.9,
        },
        api_key_configured: false,
        api_key_hint: '',
      },
      saving: false,
      testing: false,
      showApiKey: false,
      defaults: null, // 保存初始值，用于恢复默认

      providers: [],
      templates: [],
      providerLabels: {
        deepseek: 'DeepSeek',
        minimax: 'MiniMax',
        qwen: '通义千问',
        glm: '智谱 GLM',
        openai: 'OpenAI',
        claude: 'Anthropic Claude',
      },
      providerPresets: {
        deepseek: { model: 'deepseek-chat', base_url: 'https://api.deepseek.com/v1' },
        minimax: { model: 'MiniMax-Text-01', base_url: '' },
        qwen: { model: 'qwen-plus', base_url: '' },
        glm: { model: 'glm-4', base_url: '' },
        openai: { model: 'gpt-4o-mini', base_url: '' },
        claude: { model: 'claude-sonnet-4-6', base_url: '' },
      },
      temperatureLabels: {
        knowledge_points: '知识点',
        content_summary: '内容概述',
        homework: '作业',
        vocabulary: '单词',
        ability_improvement: '能力提高',
        evaluation: '评价',
      },

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
    _defaultTemperature() {
      return {
        knowledge_points: 0.3,
        content_summary: 0.5,
        homework: 0.5,
        vocabulary: 0.5,
        ability_improvement: 0.5,
        evaluation: 0.9,
      };
    },

    buildPayload() {
      const payload = {};
      for (const [key, value] of Object.entries(this.form)) {
        if (key !== 'api_key_configured' && key !== 'api_key_hint') {
          payload[key] = value;
        }
      }
      return payload;
    },

    async loadSettings() {
      try {
        const [data, providers, templates] = await Promise.all([
          API.settings.get(),
          API.ai.providers().catch(() => []),
          API.templates.list().catch(() => []),
        ]);
        this.providers = providers || [];
        this.templates = templates || [];
        this.form = {
          ...this.form,
          ...data,
          llm_api_key: '', // 服务端不会返回明文 Key
          llm_temperature: { ...this._defaultTemperature(), ...(data.llm_temperature || {}) },
        };
        if (!this.form.default_template_id && this.templates.length) {
          this.form.default_template_id = this.templates[0].id;
        }
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
        const result = await API.settings.save(this.buildPayload());
        this.form = { ...this.form, ...result, llm_api_key: '' };
        this.$message.success('设置已保存');
        return true;
      } catch (e) {
        this.$message.error('保存设置失败: ' + e.message);
        return false;
      } finally {
        this.saving = false;
      }
    },

    async saveAndTest() {
      if (!(await this.saveSettings())) return;
      this.testing = true;
      try {
        const result = await API.ai.testConnection();
        if (result.success) {
          this.$message.success('连接成功：' + (result.message || result.provider));
        } else {
          this.$message.error('连接失败：' + (result.message || '未知错误'));
        }
      } catch (e) {
        this.$message.error('测试连接失败: ' + e.message);
      } finally {
        this.testing = false;
      }
    },

    clearApiKey() {
      this.$confirm('清除后需要重新填写 API Key 才能生成内容，确定继续？', '提示', {
        type: 'warning',
        confirmButtonText: '清除',
        cancelButtonText: '取消',
      }).then(async () => {
        try {
          const result = await API.settings.save({ llm_api_key: null });
          this.form = { ...this.form, ...result, llm_api_key: '' };
          this.$message.success('已清除 API Key');
        } catch (e) {
          this.$message.error('清除失败: ' + e.message);
        }
      }).catch(() => {});
    },

    onProviderChange(provider) {
      const preset = this.providerPresets[provider] || {};
      if (preset.model) this.form.llm_default_model = preset.model;
      if (preset.base_url !== undefined) this.form.llm_base_url = preset.base_url;
    },

    resetToDefaults() {
      if (!this.form.image_dpi) return;
      this.form = {
        ...this.form,
        default_project_dir: '',
        custom_output_dir: '',
        image_dpi: 150,
        image_quality: 95,
        image_enabled: true,
        auto_save_interval_seconds: 30,
        llm_provider: 'deepseek',
        llm_base_url: '',
        llm_default_model: 'deepseek-chat',
        llm_max_tokens: 8192,
        llm_timeout: 60,
        llm_max_retries: 2,
        llm_thinking_enabled: false,
        llm_temperature: this._defaultTemperature(),
        // 保留已保存的 API Key，恢复默认不会清除密钥
        llm_api_key: '',
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
