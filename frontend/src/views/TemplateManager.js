/**
 * 模板管理组件
 * 列出所有模板，支持创建/编辑/删除自定义模板
 */
const TemplateManagerView = {
  template: `
    <div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h2 style="margin:0;">🎨 模板管理</h2>
        <div style="display:flex;gap:8px;">
          <el-button type="primary" @click="showCreateDialog">
            <el-icon><Plus /></el-icon> 创建模板
          </el-button>
          <el-button type="success" @click="showUploadDialog">
            <el-icon><UploadFilled /></el-icon> 上传模板
          </el-button>
        </div>
      </div>

      <!-- 内置模板区 -->
      <el-card class="section-card">
        <template #header>
          <div style="display:flex;align-items:center;gap:6px;">
            <el-icon size="16"><FolderOpened /></el-icon>
            <span>内置模板</span>
          </div>
        </template>
        <div v-if="loading" style="text-align:center;padding:30px;">
          <el-icon class="is-loading" :size="24"><Loading /></el-icon>
          <p style="margin-top:8px;color:#909399;">加载中...</p>
        </div>
        <el-table v-else :data="builtinTemplates" stripe style="width:100%">
          <el-table-column prop="name" label="模板名称" width="140" />
          <el-table-column prop="id" label="标识" width="120" />
          <el-table-column prop="description" label="描述" min-width="200" />
          <el-table-column prop="page_size" label="页面" width="70" />
          <el-table-column label="操作" width="130">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="previewTemplate(row.id)">预览</el-button>
              <el-button size="small" type="success" link @click="cloneFromBuiltin(row)">以此创建</el-button>
              <el-button size="small" link @click="setDefault(row)" :type="defaultTemplateId === row.id ? 'warning' : 'default'">
                {{ defaultTemplateId === row.id ? '⭐ 默认' : '设为默认' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 自定义模板区 -->
      <el-card class="section-card" style="margin-top:16px;">
        <template #header>
          <div style="display:flex;align-items:center;gap:6px;">
            <el-icon size="16"><Folder /></el-icon>
            <span>我的模板</span>
          </div>
        </template>
        <div v-if="customTemplates.length === 0" style="text-align:center;padding:30px;color:#909399;">
          <el-icon :size="24" style="vertical-align:middle;"><FolderAdd /></el-icon>
          <p style="margin-top:8px;">暂无自定义模板，点击上方"创建模板"开始</p>
        </div>
        <el-table v-else :data="customTemplates" stripe style="width:100%">
          <el-table-column prop="name" label="模板名称" width="140" />
          <el-table-column prop="id" label="标识" width="120" />
          <el-table-column label="基于" width="90">
            <template #default="{ row }">
              {{ row.parent_template || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="160" />
          <el-table-column prop="page_size" label="页面" width="70" />
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="editTemplate(row)">编辑</el-button>
              <el-button size="small" link @click="previewTemplate(row.id)">预览</el-button>
              <el-button size="small" type="danger" link @click="confirmDelete(row)">删除</el-button>
              <el-button size="small" link @click="setDefault(row)" :type="defaultTemplateId === row.id ? 'warning' : 'default'">
                {{ defaultTemplateId === row.id ? '⭐ 默认' : '设为默认' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- ======================== 创建对话框 ======================== -->
      <el-dialog v-model="createDialogVisible" title="创建模板" width="560px"
        :close-on-click-modal="false">
        <el-form :model="createForm" label-width="100px" size="small">
          <el-form-item label="模板名称" required>
            <el-input v-model="createForm.name" placeholder="输入模板名称" maxlength="50" show-word-limit />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="createForm.description" type="textarea" :rows="2"
              maxlength="200" show-word-limit placeholder="简短描述模板风格和用途" />
          </el-form-item>
          <el-form-item label="基础模板" required>
            <el-select v-model="createForm.base_template_id" placeholder="选择基础模板" style="width:100%">
              <el-option v-for="t in allTemplates" :key="t.id" :label="t.name" :value="t.id">
                <span>{{ t.name }}</span>
                <span style="float:right;color:#909399;font-size:12px;"
                  :class="t.is_builtin ? 'tag-builtin' : 'tag-custom'">
                  {{ t.is_builtin ? '内置' : '自定义' }}
                </span>
              </el-option>
            </el-select>
          </el-form-item>

          <el-divider content-position="left">主题设置 <span style="color:#909399;font-size:12px;">（留空则继承基础模板）</span></el-divider>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="主色" label-width="60px">
              <div style="display:flex;gap:6px;align-items:center;">
                <el-color-picker v-model="createForm.primary_color" show-alpha />
                <el-input v-model="createForm.primary_color" size="small" style="width:90px;" />
              </div>
            </el-form-item>
            <el-form-item label="辅色" label-width="60px">
              <div style="display:flex;gap:6px;align-items:center;">
                <el-color-picker v-model="createForm.secondary_color" show-alpha />
                <el-input v-model="createForm.secondary_color" size="small" style="width:90px;" />
              </div>
            </el-form-item>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="标题字体" label-width="60px">
              <el-select v-model="createForm.font_title" style="width:100%;" placeholder="继承">
                <el-option v-for="f in fontOptions" :key="f.value" :label="f.label" :value="f.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="正文字体" label-width="60px">
              <el-select v-model="createForm.font_body" style="width:100%;" placeholder="继承">
                <el-option v-for="f in fontOptions" :key="f.value" :label="f.label" :value="f.value" />
              </el-select>
            </el-form-item>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="标题字号" label-width="60px">
              <div style="display:flex;gap:18px;align-items:center;">
                <el-slider v-model="createForm.font_size_title" :min="12" :max="48" :show-tooltip="false" style="width:100px;" />
                <span style="white-space:nowrap;">{{ createForm.font_size_title }}pt</span>
              </div>
            </el-form-item>
            <el-form-item label="正文字号" label-width="60px">
              <div style="display:flex;gap:18px;align-items:center;">
                <el-slider v-model="createForm.font_size_body" :min="8" :max="20" :show-tooltip="false" style="width:100px;" />
                <span style="white-space:nowrap;">{{ createForm.font_size_body }}pt</span>
              </div>
            </el-form-item>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="背景色" label-width="60px">
              <div style="display:flex;gap:6px;align-items:center;">
                <el-color-picker v-model="createForm.background_color" show-alpha />
                <el-input v-model="createForm.background_color" size="small" style="width:90px;" />
              </div>
            </el-form-item>
          </div>
          <!-- 背景图上传 -->
          <el-form-item label="背景图" label-width="60px">
            <div>
              <el-upload
                :show-file-list="false"
                :before-upload="(file) => handleCreateBgUpload(file)"
                accept="image/png,image/jpeg,image/webp">
                <el-button size="small" type="primary">选择图片</el-button>
                <span style="color:#909399;font-size:12px;margin-left:8px;">建议 1920×1080 以上</span>
              </el-upload>
              <div v-if="createForm.background_image" class="bg-preview" style="margin-top:8px;position:relative;display:inline-block;">
                <img :src="createForm.background_image" style="max-height:60px;border-radius:4px;border:1px solid #dcdfe6;" />
                <el-button size="small" circle type="danger"
                  style="position:absolute;top:-8px;right:-8px;width:18px;height:18px;min-height:18px;padding:0;"
                  @click="createForm.background_image = null">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
            </div>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button @click="previewCreate" :disabled="!createForm.base_template_id">
            👁️ 预览效果
          </el-button>
          <el-button type="primary" @click="submitCreate" :loading="creating">
            创建
          </el-button>
        </template>
      </el-dialog>

      <!-- ======================== 编辑对话框 ======================== -->
      <el-dialog v-model="editDialogVisible" title="编辑模板" width="560px"
        :close-on-click-modal="false">
        <el-form :model="editForm" label-width="100px" size="small">
          <el-form-item label="模板名称" required>
            <el-input v-model="editForm.name" maxlength="50" show-word-limit />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="editForm.description" type="textarea" :rows="2"
              maxlength="200" show-word-limit />
          </el-form-item>

          <el-divider content-position="left">主题设置</el-divider>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="主色" label-width="60px">
              <div style="display:flex;gap:6px;align-items:center;">
                <el-color-picker v-model="editForm.primary_color" show-alpha />
                <el-input v-model="editForm.primary_color" size="small" style="width:90px;" />
              </div>
            </el-form-item>
            <el-form-item label="辅色" label-width="60px">
              <div style="display:flex;gap:6px;align-items:center;">
                <el-color-picker v-model="editForm.secondary_color" show-alpha />
                <el-input v-model="editForm.secondary_color" size="small" style="width:90px;" />
              </div>
            </el-form-item>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="标题字体" label-width="60px">
              <el-select v-model="editForm.font_title" style="width:100%;">
                <el-option v-for="f in fontOptions" :key="f.value" :label="f.label" :value="f.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="正文字体" label-width="60px">
              <el-select v-model="editForm.font_body" style="width:100%;">
                <el-option v-for="f in fontOptions" :key="f.value" :label="f.label" :value="f.value" />
              </el-select>
            </el-form-item>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="标题字号" label-width="60px">
              <div style="display:flex;gap:18px;align-items:center;">
                <el-slider v-model="editForm.font_size_title" :min="12" :max="48" :show-tooltip="false" style="width:100px;" />
                <span style="white-space:nowrap;">{{ editForm.font_size_title }}pt</span>
              </div>
            </el-form-item>
            <el-form-item label="正文字号" label-width="60px">
              <div style="display:flex;gap:18px;align-items:center;">
                <el-slider v-model="editForm.font_size_body" :min="8" :max="20" :show-tooltip="false" style="width:100px;" />
                <span style="white-space:nowrap;">{{ editForm.font_size_body }}pt</span>
              </div>
            </el-form-item>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="背景色" label-width="60px">
              <div style="display:flex;gap:6px;align-items:center;">
                <el-color-picker v-model="editForm.background_color" show-alpha />
                <el-input v-model="editForm.background_color" size="small" style="width:90px;" />
              </div>
            </el-form-item>
          </div>
          <!-- 背景图上传 -->
          <el-form-item label="背景图" label-width="60px">
            <div>
              <el-upload
                :show-file-list="false"
                :before-upload="(file) => handleEditBgUpload(file)"
                accept="image/png,image/jpeg,image/webp">
                <el-button size="small" type="primary">选择图片</el-button>
                <span style="color:#909399;font-size:12px;margin-left:8px;">建议 1920×1080 以上</span>
              </el-upload>
              <div v-if="editForm.background_image" class="bg-preview" style="margin-top:8px;position:relative;display:inline-block;">
                <img :src="editForm.background_image" style="max-height:60px;border-radius:4px;border:1px solid #dcdfe6;" />
                <el-button size="small" circle type="danger"
                  style="position:absolute;top:-8px;right:-8px;width:18px;height:18px;min-height:18px;padding:0;"
                  @click="editForm.background_image = null">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
            </div>
          </el-form-item>
          <el-divider content-position="left">页面边距 <span style="color:#909399;font-size:12px;">（防止内容覆盖背景图边框）</span></el-divider>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="上边距" label-width="60px">
              <div style="display:flex;gap:18px;align-items:center;">
                <el-slider v-model="editForm.page_margin_top" :min="5" :max="40" :show-tooltip="false" style="width:100px;" />
                <span style="white-space:nowrap;width:40px;">{{ editForm.page_margin_top }}mm</span>
              </div>
            </el-form-item>
            <el-form-item label="下边距" label-width="60px">
              <div style="display:flex;gap:18px;align-items:center;">
                <el-slider v-model="editForm.page_margin_bottom" :min="5" :max="40" :show-tooltip="false" style="width:100px;" />
                <span style="white-space:nowrap;width:40px;">{{ editForm.page_margin_bottom }}mm</span>
              </div>
            </el-form-item>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="左边距" label-width="60px">
              <div style="display:flex;gap:18px;align-items:center;">
                <el-slider v-model="editForm.page_margin_left" :min="5" :max="40" :show-tooltip="false" style="width:100px;" />
                <span style="white-space:nowrap;width:40px;">{{ editForm.page_margin_left }}mm</span>
              </div>
            </el-form-item>
            <el-form-item label="右边距" label-width="60px">
              <div style="display:flex;gap:18px;align-items:center;">
                <el-slider v-model="editForm.page_margin_right" :min="5" :max="40" :show-tooltip="false" style="width:100px;" />
                <span style="white-space:nowrap;width:40px;">{{ editForm.page_margin_right }}mm</span>
              </div>
            </el-form-item>
          </div>
          <el-divider content-position="left">Logo 设置</el-divider>
          <el-form-item label="Logo 图片" label-width="80px">
            <div>
              <el-upload
                :show-file-list="false"
                :before-upload="(file) => handleEditLogoUpload(file)"
                accept="image/png,image/jpeg,image/webp">
                <el-button size="small" type="primary">上传 Logo</el-button>
              </el-upload>
              <div v-if="editForm.logo_data_uri" class="logo-preview" style="margin-top:8px;position:relative;display:inline-block;">
                <img :src="editForm.logo_data_uri" style="max-height:50px;border-radius:4px;border:1px solid #dcdfe6;" />
                <el-button size="small" circle type="danger"
                  style="position:absolute;top:-8px;right:-8px;width:18px;height:18px;min-height:18px;padding:0;"
                  @click="editForm.logo_data_uri = null">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="显示 Logo" label-width="80px">
            <el-switch v-model="editForm.logo_config.enabled" />
          </el-form-item>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <el-form-item label="位置" label-width="60px">
              <el-select v-model="editForm.logo_config.position" style="width:100%;">
                <el-option label="左上" value="top-left" />
                <el-option label="右上" value="top-right" />
                <el-option label="上中" value="top-center" />
                <el-option label="左下" value="bottom-left" />
                <el-option label="右下" value="bottom-right" />
                <el-option label="下中" value="bottom-center" />
              </el-select>
            </el-form-item>
            <el-form-item label="尺寸" label-width="60px">
              <div style="display:flex;gap:18px;align-items:center;">
                <el-slider v-model="editForm.logo_config.size" :min="10" :max="80" :show-tooltip="false" style="width:100px;" />
                <span style="white-space:nowrap;width:40px;">{{ editForm.logo_config.size }}mm</span>
              </div>
            </el-form-item>
          </div>
          <el-form-item label="每页显示" label-width="80px">
            <el-switch v-model="editForm.logo_config.show_on_all_pages" />
          </el-form-item>
          <el-form-item label="Logo 边距" label-width="80px">
            <div style="display:flex;gap:18px;align-items:center;">
              <el-slider v-model="editForm.logo_config.margin" :min="0" :max="20" :show-tooltip="false" style="width:100px;" />
              <span style="white-space:nowrap;width:40px;">{{ editForm.logo_config.margin }}mm</span>
            </div>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editDialogVisible = false">取消</el-button>
          <el-button @click="previewEdit()">👁️ 预览</el-button>
          <el-button type="primary" @click="submitEdit" :loading="saving">保存</el-button>
        </template>
      </el-dialog>

      <!-- ======================== 上传对话框 ======================== -->
      <el-dialog v-model="uploadDialogVisible" title="上传模板" width="420px"
        :close-on-click-modal="false">
        <el-upload
          drag
          accept=".zip"
          :auto-upload="false"
          :limit="1"
          :on-change="handleUploadChange"
          :on-exceed="handleUploadExceed"
          ref="uploadRef">
          <el-icon :size="40" style="color:#409eff;"><UploadFilled /></el-icon>
          <div style="margin-top:8px;">将 .zip 模板文件拖拽到这里，或 <em>点击选择</em></div>
          <template #tip>
            <div style="color:#909399;font-size:12px;margin-top:4px;">
              要求：zip 内包含 config.json, template.html, style.css（无子目录）
            </div>
          </template>
        </el-upload>
        <div v-if="uploadResult" :style="{
          marginTop: '12px', padding: '10px', borderRadius: '4px',
          background: uploadSuccess ? '#f0f9eb' : '#fef0f0',
          color: uploadSuccess ? '#67c23a' : '#f56c6c'
        }">
          {{ uploadResult }}
        </div>
        <template #footer>
          <el-button @click="uploadDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitUpload"
            :loading="uploading" :disabled="!uploadFile">
            {{ uploading ? '上传中...' : '开始上传' }}
          </el-button>
        </template>
      </el-dialog>

      <!-- ======================== 预览弹窗 ======================== -->
      <el-dialog v-model="previewDialogVisible" title="模板预览" width="90%" top="2vh"
        :close-on-click-modal="false">
        <div v-if="previewLoading" style="text-align:center;padding:40px;">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          <p style="margin-top:12px;color:#909399;">正在生成预览...</p>
        </div>
        <div v-else-if="previewError" style="color:#f56c6c;padding:30px;text-align:center;">
          {{ previewError }}
        </div>
        <iframe v-else-if="previewHtml"
          :srcdoc="previewHtml"
          style="width:100%;height:75vh;border:1px solid #dcdfe6;border-radius:4px;" />
        <template #footer>
          <el-button @click="previewDialogVisible = false">关闭</el-button>
        </template>
      </el-dialog>
    </div>
  `,

  data() {
    return {
      allTemplates: [],
      builtinTemplates: [],
      customTemplates: [],
      loading: false,

      // 创建对话框
      createDialogVisible: false,
      creating: false,
      createForm: this._emptyCreateForm(),

      // 编辑对话框
      editDialogVisible: false,
      editingTemplateId: null,
      saving: false,
      editForm: this._emptyEditForm(),

      // 预览
      previewDialogVisible: false,
      previewHtml: '',
      previewLoading: false,
      previewError: '',

      // 上传
      uploadDialogVisible: false,
      uploading: false,
      uploadFile: null,
      uploadResult: '',
      uploadSuccess: false,

      // 字体选项
      defaultTemplateId: localStorage.getItem('crg_default_template') || '',
      fontOptions: [
        { value: 'Heiti SC', label: '黑体' },
        { value: 'STSong', label: '宋体' },
        { value: 'PingFang SC', label: '苹方' },
        { value: 'SimSun', label: '宋体(SimSun)' },
        { value: 'Microsoft YaHei', label: '微软雅黑' },
        { value: 'KaiTi', label: '楷体' },
        { value: 'FangSong', label: '仿宋' },
        { value: 'STKaiti', label: '华文楷体' },
        { value: 'STXihei', label: '华文细黑' },
      ],
    };
  },

  async mounted() {
    this.Router = Router;
    await this.loadTemplates();
  },

  methods: {
    async loadTemplates() {
      this.loading = true;
      try {
        const list = await API.templates.list();
        this.allTemplates = list;
        this.builtinTemplates = list.filter(t => t.is_builtin);
        this.customTemplates = list.filter(t => !t.is_builtin);
      } catch (e) {
        this.$message.error('加载模板列表失败: ' + e.message);
      } finally {
        this.loading = false;
      }
    },

    _emptyCreateForm() {
      return {
        name: '',
        description: '',
        base_template_id: '',
        primary_color: null,
        secondary_color: null,
        font_title: null,
        font_body: null,
        font_size_title: 24,
        font_size_body: 11,
        background_color: null,
        background_image: null,
      };
    },

    _emptyEditForm() {
      return {
        name: '',
        description: '',
        primary_color: '#3B7DDD',
        secondary_color: '#F5F5F5',
        font_title: 'Heiti SC',
        font_body: 'STSong',
        font_size_title: 24,
        font_size_body: 11,
        background_color: '#FFFFFF',
        background_image: null,
        page_margin_top: 20,
        page_margin_bottom: 18,
        page_margin_left: 18,
        page_margin_right: 18,
        logo_config: { enabled: true, position: 'top-right', size: 30, show_on_all_pages: true, margin: 0 },
        logo_data_uri: null,
        page_size: 'A4',
      };
    },

    showCreateDialog() {
      this.createForm = this._emptyCreateForm();
      if (this.builtinTemplates.length > 0) {
        this.createForm.base_template_id = this.builtinTemplates[0].id;
      }
      this.createDialogVisible = true;
    },

    cloneFromBuiltin(template) {
      this.createForm = this._emptyCreateForm();
      this.createForm.name = template.name + '_副本';
      this.createForm.base_template_id = template.id;
      this.createDialogVisible = true;
    },

    async editTemplate(template) {
      this.editingTemplateId = template.id;
      this.editForm = {
        name: template.name,
        description: template.description || '',
        primary_color: '#3B7DDD',
        secondary_color: '#F5F5F5',
        font_title: 'Heiti SC',
        font_body: 'STSong',
        font_size_title: 24,
        font_size_body: 11,
        background_color: '#FFFFFF',
        background_image: null,
        page_margin_top: 20,
        page_margin_bottom: 18,
        page_margin_left: 18,
        page_margin_right: 18,
        logo_config: { enabled: true, position: 'top-right', size: 30, show_on_all_pages: true, margin: 0 },
        logo_data_uri: null,
        page_size: template.page_size || 'A4',
      };
      // 加载完整配置以获取当前主题值
      try {
        const config = await API.templates.getConfig(template.id);
        if (config) {
          if (config.theme) {
            const t = config.theme;
            if (t.primary_color) this.editForm.primary_color = t.primary_color;
            if (t.secondary_color) this.editForm.secondary_color = t.secondary_color;
            if (t.font_title) this.editForm.font_title = t.font_title;
            if (t.font_body) this.editForm.font_body = t.font_body;
            if (t.font_size_title) this.editForm.font_size_title = t.font_size_title;
            if (t.font_size_body) this.editForm.font_size_body = t.font_size_body;
            if (t.background_color) this.editForm.background_color = t.background_color;
            if (t.background_image) this.editForm.background_image = t.background_image;
            if (t.page_margin_top !== undefined) this.editForm.page_margin_top = t.page_margin_top;
            if (t.page_margin_bottom !== undefined) this.editForm.page_margin_bottom = t.page_margin_bottom;
            if (t.page_margin_left !== undefined) this.editForm.page_margin_left = t.page_margin_left;
            if (t.page_margin_right !== undefined) this.editForm.page_margin_right = t.page_margin_right;
          }
          if (config.logo_config) {
            Object.assign(this.editForm.logo_config, config.logo_config);
            if (typeof this.editForm.logo_config.size === 'string') {
              this.editForm.logo_config.size = {small: 20, medium: 30, large: 45}[this.editForm.logo_config.size] || 30;
            }
          }
          if (config.logo_data_uri) {
            this.editForm.logo_data_uri = config.logo_data_uri;
          }
        }
      } catch (_) { /* 忽略加载失败，使用默认值 */ }
      this.editDialogVisible = true;
    },

    _buildThemeOverrides(form) {
      const overrides = {};
      const keys = ['primary_color', 'secondary_color', 'font_title', 'font_body',
                    'font_size_title', 'font_size_body', 'background_color', 'background_image',
                    'page_margin_top', 'page_margin_bottom', 'page_margin_left', 'page_margin_right'];
      for (const key of keys) {
        if (form[key] !== null && form[key] !== undefined && form[key] !== '') {
          overrides[key] = form[key];
        }
      }
      return overrides;
    },

    handleCreateBgUpload(file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        this.createForm.background_image = e.target.result;
      };
      reader.readAsDataURL(file);
      return false; // 阻止默认上传
    },

    handleEditBgUpload(file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        this.editForm.background_image = e.target.result;
      };
      reader.readAsDataURL(file);
      return false; // 阻止默认上传
    },

    handleEditLogoUpload(file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        this.editForm.logo_data_uri = e.target.result;
      };
      reader.readAsDataURL(file);
      return false; // 阻止默认上传
    },

    async submitCreate() {
      if (!this.createForm.name.trim()) {
        this.$message.warning('请输入模板名称');
        return;
      }
      if (!this.createForm.base_template_id) {
        this.$message.warning('请选择基础模板');
        return;
      }
      this.creating = true;
      try {
        const payload = {
          name: this.createForm.name.trim(),
          description: this.createForm.description.trim(),
          base_template_id: this.createForm.base_template_id,
          theme_overrides: this._buildThemeOverrides(this.createForm),
        };
        await API.templates.create(payload);
        this.$message.success('模板创建成功');
        this.createDialogVisible = false;
        await this.loadTemplates();
      } catch (e) {
        this.$message.error('创建失败: ' + e.message);
      } finally {
        this.creating = false;
      }
    },

    async submitEdit() {
      if (!this.editForm.name.trim()) {
        this.$message.warning('模板名称不能为空');
        return;
      }
      this.saving = true;
      try {
        const payload = {
          name: this.editForm.name.trim(),
          description: this.editForm.description.trim(),
          page_size: this.editForm.page_size,
          logo_config: this.editForm.logo_config,
          logo_data_uri: this.editForm.logo_data_uri || null,
          ...this._buildThemeOverrides(this.editForm),
        };
        await API.templates.update(this.editingTemplateId, payload);
        this.$message.success('模板已更新');
        this.editDialogVisible = false;
        await this.loadTemplates();
      } catch (e) {
        this.$message.error('更新失败: ' + e.message);
      } finally {
        this.saving = false;
      }
    },

    async previewTemplate(templateId, themeOverrides = null) {
      if (!templateId) {
        this.$message.warning('请选择要预览的模板');
        return;
      }
      this.previewDialogVisible = true;
      this.previewLoading = true;
      this.previewError = '';
      this.previewHtml = '';
      try {
        const html = await API.templates.preview(templateId, themeOverrides);
        this.previewHtml = html;
      } catch (e) {
        this.previewError = '预览失败: ' + e.message;
      } finally {
        this.previewLoading = false;
      }
    },

    /** 从 editForm 构建实时预览的 theme_overrides */
    _buildPreviewOverrides(form) {
      const overrides = this._buildThemeOverrides(form);
      if (form.logo_data_uri) {
        overrides.logo_data_uri = form.logo_data_uri;
      }
      if (form.logo_config && form.logo_config.margin !== undefined) {
        overrides.logo_margin = form.logo_config.margin;
      }
      if (form.logo_config && form.logo_config.size !== undefined) {
        overrides.logo_size = form.logo_config.size;
      }
      return overrides;
    },

    /** 编辑对话框中预览（带着未保存的改动） */
    previewEdit() {
      this.previewTemplate(this.editingTemplateId, this._buildPreviewOverrides(this.editForm));
    },

    /** 创建对话框中预览（带着未保存的主题设置） */
    previewCreate() {
      this.previewTemplate(this.createForm.base_template_id, this._buildPreviewOverrides(this.createForm));
    },

    setDefault(template) {
      localStorage.setItem('crg_default_template', template.id);
      this.defaultTemplateId = template.id;
      this.$message.success(`已将「${template.name}」设为默认模板`);
    },

    confirmDelete(template) {
      this.$confirm(
        `确定删除模板「${template.name}」？\n此操作不可撤销。`,
        '确认删除',
        {
          type: 'warning',
          confirmButtonText: '删除',
          cancelButtonText: '取消',
        }
      ).then(async () => {
        try {
          await API.templates.delete(template.id);
          this.$message.success('已删除');
          await this.loadTemplates();
        } catch (e) {
          this.$message.error('删除失败: ' + e.message);
        }
      }).catch(() => {});
    },

    showUploadDialog() {
      this.uploadDialogVisible = true;
      this.uploadFile = null;
      this.uploadResult = '';
      this.uploadSuccess = false;
    },

    handleUploadChange(file) {
      this.uploadFile = file.raw;
      this.uploadResult = '';
    },

    handleUploadExceed() {
      this.$message.warning('每次只能上传一个文件');
    },

    async submitUpload() {
      if (!this.uploadFile) {
        this.$message.warning('请先选择要上传的模板文件');
        return;
      }
      this.uploading = true;
      this.uploadResult = '';
      try {
        const result = await API.templates.uploadTemplate(this.uploadFile);
        this.uploadSuccess = true;
        this.uploadResult = `✅ 模板「${result.name}」上传成功！`;
        this.$message.success('模板上传成功');
        this.uploadFile = null;
        await this.loadTemplates();
        setTimeout(() => { this.uploadDialogVisible = false; }, 1500);
      } catch (e) {
        this.uploadSuccess = false;
        this.uploadResult = '❌ ' + e.message;
        this.$message.error('上传失败: ' + e.message);
      } finally {
        this.uploading = false;
      }
    },
  },
};
