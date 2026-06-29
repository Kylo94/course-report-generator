/**
 * 批量报告生成页面（编辑器风格）
 * 左侧编辑共享内容（知识点、内容概述、作业、单词等），
 * 下方以表格展示各学生评价（可编辑），右侧操作栏
 */
const BatchReportView = {
  template: `
    <div>
      <!-- 未选择班级时的选择界面 -->
      <div v-if="!config.class_id" class="empty-state">
        <h3 style="margin-bottom:20px;">批量生成报告</h3>
        <el-select v-model="selectedClassId" filterable placeholder="请选择班级" style="width:300px"
          @change="onClassSelected">
          <el-option v-for="c in classList" :key="c.id"
            :label="c.name + '（' + (c.student_count || 0) + '人）'" :value="c.id" />
        </el-select>
      </div>

      <!-- 编辑器主体 -->
      <div v-else class="editor-layout">
        <!-- 左侧：共享内容编辑 -->
        <div class="editor-main">

          <!-- 基本信息 -->
          <el-card class="section-card">
            <template #header>
              <span>📋 基本信息 — {{ className }}（{{ studentCount }} 名学生）</span>
              <el-button size="small" link style="float:right" @click="changeClass">更换班级</el-button>
            </template>
            <el-form label-width="100px" size="small">
              <el-form-item label="上课日期">
                <el-date-picker v-model="config.course_date" type="date" placeholder="选择日期"
                  value-format="YYYY-MM-DD" style="width:200px" />
              </el-form-item>
              <el-form-item label="课程名称">
                <el-input v-model="config.course_topic" maxlength="10" show-word-limit style="width:300px"
                  placeholder="≤10 字" />
              </el-form-item>
              <el-form-item label="项目文件夹">
                <div style="display:flex;gap:8px;width:100%;">
                  <el-input v-model="config.project_folder" placeholder="输入项目文件夹绝对路径，或点击📂浏览" style="flex:1" />
                  <el-button @click="openDirBrowser">📂 浏览</el-button>
                </div>
              </el-form-item>
              <el-form-item label="教师观察">
                <el-input v-model="config.teacher_observation" type="textarea" :rows="2"
                  maxlength="300" show-word-limit
                  placeholder="输入对班级整体的课堂观察，AI 评价将参考此信息" style="width:400px" />
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 知识点概括 -->
          <el-card class="section-card">
            <template #header>
              <span>🎯 知识点概括（≤5条，每条≤15字）</span>
              <el-button size="small" type="warning" link style="float:right"
                :disabled="batchRunning" @click="regenerateField('knowledge_points')">
                {{ regeneratingFields['knowledge_points'] ? '生成中...' : '重新生成' }}
              </el-button>
            </template>
            <div class="kp-tags">
              <el-tag v-for="(kp, i) in sharedContent.knowledge_points" :key="i"
                closable :disable-transitions="false" @close="removeKp(i)">
                {{ kp }}
              </el-tag>
              <el-input v-if="kpInputVisible" ref="kpInputRef" v-model="kpInputValue"
                class="kp-tag-input" size="small" maxlength="15" show-word-limit
                @keyup.enter="confirmKp" @blur="confirmKp" />
              <el-button v-else size="small" @click="showKpInput"
                :disabled="sharedContent.knowledge_points.length >= 5">
                + 添加
              </el-button>
            </div>
          </el-card>

          <!-- 能力提升 -->
          <el-card class="section-card">
            <template #header>
              <span>💪 能力提升</span>
              <el-button size="small" type="warning" link style="float:right"
                :disabled="batchRunning" @click="regenerateField('ability_improvement')">
                {{ regeneratingFields['ability_improvement'] ? '生成中...' : '重新生成' }}
              </el-button>
            </template>
            <el-input v-model="sharedContent.ability_improvement" type="textarea" :rows="2"
              show-word-limit placeholder="输入能力提升" />
          </el-card>

          <!-- 内容概述 -->
          <el-card class="section-card">
            <template #header>
              <span>📝 内容概述</span>
              <el-button size="small" type="warning" link style="float:right"
                :disabled="batchRunning" @click="regenerateField('content_summary')">
                {{ regeneratingFields['content_summary'] ? '生成中...' : '重新生成' }}
              </el-button>
            </template>
            <div v-if="!sharedContent.content_items || sharedContent.content_items.length === 0" style="color:#909399;">
              暂无内容，请先通过 AI 生成或手动添加
            </div>
            <div v-for="(item, i) in sharedContent.content_items" :key="i" class="content-item">
              <div class="content-item-header">
                {{ item.kp }}
                <el-button size="small" type="danger" link @click="removeContentItem(i)">删除</el-button>
              </div>
              <el-input v-model="item.text" type="textarea" :rows="3"
                maxlength="200" show-word-limit />
            </div>
          </el-card>

          <!-- 单词学习 -->
          <el-card class="section-card">
            <template #header>
              <span>📖 单词学习</span>
              <el-button size="small" type="warning" link style="float:right"
                :disabled="batchRunning" @click="regenerateField('homework_vocab')">
                {{ regeneratingFields['homework_vocab'] ? '生成中...' : '重新生成' }}
              </el-button>
            </template>
            <el-form label-width="100px" size="small">
              <el-form-item label="单词">
                <el-input v-model="sharedContent.vocabulary.word" style="width:200px" />
              </el-form-item>
              <el-form-item label="音标">
                <el-input v-model="sharedContent.vocabulary.phonetic" style="width:200px" />
              </el-form-item>
              <el-form-item label="释义">
                <el-input v-model="sharedContent.vocabulary.meaning" style="width:300px" />
              </el-form-item>
              <el-form-item label="例句">
                <el-input v-model="sharedContent.vocabulary.example" type="textarea" :rows="2" style="width:400px" />
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 课后作业 -->
          <el-card class="section-card">
            <template #header>
              <span>📚 课后作业</span>
              <el-button size="small" type="warning" link style="float:right"
                :disabled="batchRunning" @click="regenerateField('homework_vocab')">
                {{ regeneratingFields['homework_vocab'] ? '生成中...' : '重新生成' }}
              </el-button>
            </template>
            <el-form label-width="100px" size="small">
              <el-form-item label="作业目标">
                <el-input v-model="sharedContent.homework.goal" type="textarea" :rows="2" style="width:400px" />
              </el-form-item>
              <el-form-item label="提示">
                <div v-for="(h, i) in sharedContent.homework.hints" :key="'h'+i" style="margin-bottom:4px">
                  <el-input v-model="sharedContent.homework.hints[i]" style="width:300px" placeholder="提示内容">
                    <template #prefix>#{{ i+1 }}</template>
                    <template #suffix>
                      <el-button link type="danger" size="small" @click="removeHint(i)">×</el-button>
                    </template>
                  </el-input>
                </div>
                <el-button size="small" @click="addHint">+ 添加提示</el-button>
              </el-form-item>
              <el-form-item label="评分点">
                <div v-for="(c, i) in sharedContent.homework.criteria" :key="'c'+i" style="margin-bottom:4px">
                  <el-input v-model="sharedContent.homework.criteria[i]" style="width:300px" placeholder="评分标准">
                    <template #prefix>#{{ i+1 }}</template>
                    <template #suffix>
                      <el-button link type="danger" size="small" @click="removeCriterion(i)">×</el-button>
                    </template>
                  </el-input>
                </div>
                <el-button size="small" @click="addCriterion">+ 添加评分点</el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 学生评价列表 -->
          <el-card class="section-card" v-if="batchResults.length > 0">
            <template #header>
              <span>⭐ 学生评价（共 {{ batchResults.length }} 人）</span>
              <el-tag size="small" :type="allEvalSuccess ? 'success' : 'warning'" style="float:right">
                {{ allEvalSuccess ? '全部成功' : successCount + '/' + batchResults.length + ' 成功' }}
              </el-tag>
            </template>
            <el-alert v-if="!allEvalSuccess"
              title="部分学生评价生成失败，可手动填写或重新生成"
              type="warning" show-icon style="margin-bottom:12px" />
            <div v-for="(r, i) in batchResults" :key="r.student_id" style="margin-bottom:12px;
              padding:12px;border:1px solid #e4e7ed;border-radius:6px;">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <strong>{{ r.student_name }}</strong>
                <span>
                  <el-tag v-if="r.error" type="danger" size="small" effect="plain">生成失败</el-tag>
                  <el-tag v-else-if="r.evaluation" type="success" size="small" effect="plain">已生成</el-tag>
                  <el-tag v-else size="info" effect="plain">待填写</el-tag>
                  <el-button v-if="r.record_id" size="small" link type="primary"
                    @click="exportSinglePdf(r)">导出PDF</el-button>
                  <el-button v-if="r.record_id" size="small" link type="info"
                    @click="previewReport(r)">预览</el-button>
                </span>
              </div>
              <el-input v-model="r.evaluation" type="textarea" :rows="3"
                maxlength="500" show-word-limit placeholder="输入该学生评价" />
              <div v-if="r.error" style="margin-top:4px;color:#f56c6c;font-size:12px;">{{ r.error }}</div>
            </div>

            <div v-if="successCount > 0" style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
              <el-button type="primary" @click="saveAllRecords" :loading="savingAll">
                💾 保存全部{{ savingAllCount > 0 ? '（已保存' + savingAllCount + '）' : '' }}
              </el-button>
              <el-button type="primary" @click="exportPdf" :loading="exporting" :disabled="batchRunning">
                📄 导出全部 PDF
              </el-button>
              <el-button @click="exportWord" :loading="wordExporting" :disabled="batchRunning">
                📝 导出全部 Word
              </el-button>
            </div>
          </el-card>
        </div>

        <!-- 右侧：侧边栏 -->
        <div class="editor-sidebar">
          <!-- 操作 -->
          <el-card class="section-card">
            <template #header>⚙️ 批量操作</template>
            <div style="display:flex;flex-direction:column;gap:8px;">
              <el-button type="primary" class="btn-feature" @click="batchGenerate" :loading="batchRunning"
                :disabled="!config.class_id" size="large">
                🚀 批量生成{{ studentCount > 0 ? '（' + studentCount + '人）' : '' }}
              </el-button>
              <div v-if="batchRunning" style="text-align:center;color:#409eff;font-size:13px;">
                {{ batchProgressText }}
                <el-progress :percentage="batchProgress" :stroke-width="12" style="margin-top:6px;" />
              </div>
            </div>
          </el-card>

          <!-- 模板选择 -->
          <el-card class="section-card">
            <template #header>🎨 模板选择</template>
            <el-radio-group v-model="config.template_id">
              <el-radio v-for="t in templateList" :key="t.id" :value="t.id" style="display:block;margin-bottom:6px;">
                {{ t.name }}
              </el-radio>
            </el-radio-group>
          </el-card>

          <!-- 截图上传 -->
          <el-card class="section-card">
            <template #header>📷 截图上传</template>
            <el-upload :http-request="handleScreenshotUpload" list-type="picture-card"
              :show-file-list="false" accept="image/jpeg,image/png,image/webp"
              :disabled="screenshotUploading">
              <el-icon><Plus /></el-icon>
            </el-upload>
            <div class="screenshot-grid">
              <div v-for="(s, i) in config.screenshot_paths" :key="i" class="screenshot-item">
                <img :src="s" alt="截图">
                <el-button class="delete-btn" size="small" circle type="danger"
                  @click="removeScreenshot(i)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
            </div>
          </el-card>

          <!-- 输出设置 -->
          <el-card class="section-card">
            <template #header>
              <el-icon size="16"><FolderOpened /></el-icon>
              <span> 输出设置</span>
            </template>
            <el-form size="small" label-position="top">
              <el-form-item label="输出目录">
                <div style="display:flex;gap:8px;">
                  <el-input v-model="config.output_dir" placeholder="留空使用默认路径" style="flex:1" />
                  <el-button @click="browseOutputDir">📂 浏览</el-button>
                </div>
              </el-form-item>
            </el-form>
          </el-card>
        </div>
      </div>

      <!-- 目录浏览器弹窗 -->
      <el-dialog v-model="showDirBrowser" title="📂 浏览文件夹" width="550px">
        <div style="margin-bottom:12px;padding:8px 12px;background:#f5f7fa;border-radius:4px;font-size:13px;word-break:break-all;color:#606266;">
          当前位置：<strong>{{ dirBrowserPath || '（常用目录）' }}</strong>
        </div>
        <div v-if="dirBrowserLoading" style="text-align:center;padding:30px;">
          <el-icon class="is-loading" size="24"><Loading /></el-icon>
          <p style="color:#909399;margin-top:8px;">加载中...</p>
        </div>
        <div v-else-if="dirBrowserError" style="color:#f56c6c;padding:16px;">
          {{ dirBrowserError }}
        </div>
        <div v-else class="dir-browser-list">
          <div v-for="item in dirBrowserItems" :key="item.path" class="dir-browser-item"
            :class="{ 'is-parent': item.is_parent }" @click="browseToDir(item.path)">
            <span>{{ item.name }}</span>
          </div>
          <div v-if="dirBrowserItems.length === 0" style="text-align:center;padding:30px;color:#909399;">
            此目录下没有子文件夹
          </div>
        </div>
        <template #footer>
          <el-button @click="showDirBrowser = false">取消</el-button>
          <el-button type="primary" @click="selectDirBrowserPath"
            :disabled="!dirBrowserPath || dirBrowserLoading">选择此文件夹</el-button>
        </template>
      </el-dialog>

      <!-- 预览弹窗 -->
      <el-dialog v-model="showPreviewDialog" title="报告预览" width="90%" top="2vh"
        :close-on-click-modal="false" @closed="previewHtml = ''">
        <div v-if="previewLoading" style="text-align:center;padding:40px;">
          <el-icon class="is-loading" size="24"><Loading /></el-icon>
          <p style="margin-top:12px;color:#909399;">正在生成预览...</p>
        </div>
        <div v-else-if="previewError" style="color:#f56c6c;padding:30px;text-align:center;">
          {{ previewError }}
        </div>
        <iframe v-else-if="previewHtml" :srcdoc="previewHtml" style="width:100%;height:75vh;border:1px solid #dcdfe6;border-radius:4px;" />
        <div v-else style="text-align:center;padding:40px;color:#909399;">暂无预览内容</div>
        <template #footer>
          <el-button @click="showPreviewDialog = false">关闭</el-button>
        </template>
      </el-dialog>
    </div>
  `,

  data() {
    return {
      selectedClassId: null,

      // 共享内容
      sharedContent: {
        knowledge_points: [],
        ability_improvement: '',
        content_items: [],
        vocabulary: { word: '', phonetic: '', meaning: '', example: '' },
        homework: { goal: '', hints: [], criteria: [] },
      },
      kpInputVisible: false,
      kpInputValue: '',
      regeneratingFields: {},

      // 目录浏览器
      showDirBrowser: false,
      dirBrowserPath: '',
      dirBrowserItems: [],
      dirBrowserLoading: false,
      dirBrowserError: null,
      _dirBrowserMode: 'project',

      config: {
        class_id: null,
        course_date: new Date().toISOString().slice(0, 10),
        course_topic: '',
        project_folder: '',
        teacher_observation: '',
        template_id: 'classic',
        output_dir: '',
        screenshot_paths: [],
      },
      classList: [],
      templateList: [],
      screenshotUploading: false,
      batchRunning: false,
      batchProgress: 0,
      batchProgressText: '',
      firstStudentId: null,
      studentList: [],
      batchResults: [],
      exporting: false,
      wordExporting: false,
      savingAll: false,
      savingAllCount: 0,
      classInfo: '',
      // 预览
      showPreviewDialog: false,
      previewHtml: '',
      previewLoading: false,
      previewError: '',
      previewRecordId: null,
    };
  },

  computed: {
    className() {
      const c = this.classList.find(cls => cls.id === this.config.class_id);
      return c ? c.name : '';
    },
    studentCount() {
      const c = this.classList.find(cls => cls.id === this.config.class_id);
      return c ? (c.student_count || 0) : 0;
    },
    successCount() {
      return this.batchResults.filter(r => !r.error).length;
    },
    allEvalSuccess() {
      return this.batchResults.length > 0 && this.successCount === this.batchResults.length;
    },
  },

  async mounted() {
    this.Router = Router;
    await this.loadClasses();
    await this.loadTemplates();
  },

  methods: {
    async loadClasses() {
      try {
        const result = await API.classes.list();
        this.classList = result.items || [];
      } catch (e) {
        this.$message.error('加载班级列表失败: ' + e.message);
      }
    },

    async loadTemplates() {
      try {
        this.templateList = await API.templates.list();
      } catch (e) {
        console.error('加载模板列表失败:', e);
      }
    },

    onClassSelected(classId) {
      this.config.class_id = classId;
      this.batchResults = [];
      this.resetSharedContent();
      this.loadFirstStudentId(classId);
    },

    async loadFirstStudentId(classId) {
      try {
        // 加载较多学生以确保覆盖目标班级的学生
        const result = await API.students.list({ page: 1, page_size: 500 });
        const students = result.items || [];
        this.studentList = students.filter(s => s.class_id === classId);
        this.firstStudentId = this.studentList.length > 0 ? this.studentList[0].id : null;
        if (!this.firstStudentId) {
          this.$message.warning('该班级暂无学生，请先添加学生');
        }
      } catch (e) {
        console.error('加载学生列表失败:', e);
      }
    },

    changeClass() {
      this.config.class_id = null;
      this.selectedClassId = null;
      this.batchResults = [];
      this.resetSharedContent();
    },

    resetSharedContent() {
      this.sharedContent = {
        knowledge_points: [],
        ability_improvement: '',
        content_items: [],
        vocabulary: { word: '', phonetic: '', meaning: '', example: '' },
        homework: { goal: '', hints: [], criteria: [] },
      };
    },

    // ===== 知识点 =====
    showKpInput() {
      this.kpInputVisible = true;
      this.$nextTick(() => {
        if (this.$refs.kpInputRef) this.$refs.kpInputRef.focus();
      });
    },
    confirmKp() {
      const v = this.kpInputValue.trim();
      if (v && !this.sharedContent.knowledge_points.includes(v) && this.sharedContent.knowledge_points.length < 5) {
        this.sharedContent.knowledge_points.push(v);
      }
      this.kpInputValue = '';
      this.kpInputVisible = false;
    },
    removeKp(i) {
      this.sharedContent.knowledge_points.splice(i, 1);
    },

    // ===== 内容项 =====
    removeContentItem(i) {
      this.sharedContent.content_items.splice(i, 1);
    },

    // ===== 作业 =====
    addHint() {
      if (!this.sharedContent.homework.hints) this.sharedContent.homework.hints = [];
      this.sharedContent.homework.hints.push('');
    },
    removeHint(i) {
      this.sharedContent.homework.hints.splice(i, 1);
    },
    addCriterion() {
      if (!this.sharedContent.homework.criteria) this.sharedContent.homework.criteria = [];
      this.sharedContent.homework.criteria.push('');
    },
    removeCriterion(i) {
      this.sharedContent.homework.criteria.splice(i, 1);
    },

    // ===== 目录浏览器 =====
    async openDirBrowser() {
      this._dirBrowserMode = 'project';
      this.dirBrowserPath = '';
      this.dirBrowserItems = [];
      this.dirBrowserError = null;
      this.showDirBrowser = true;
      const lastPath = localStorage.getItem('lastDirBrowserPath');
      await this.browseToDir(lastPath || '');
    },

    browseOutputDir() {
      this._dirBrowserMode = 'output';
      this.dirBrowserPath = this.config.output_dir || '';
      this.dirBrowserItems = [];
      this.dirBrowserError = null;
      this.showDirBrowser = true;
      const lastPath = localStorage.getItem('lastOutputDirBrowserPath');
      this.browseToDir(lastPath || '');
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
        if (result.path) {
          const key = this._dirBrowserMode === 'output' ? 'lastOutputDirBrowserPath' : 'lastDirBrowserPath';
          localStorage.setItem(key, result.path);
        }
      } catch (e) {
        this.dirBrowserError = '加载失败: ' + e.message;
      } finally {
        this.dirBrowserLoading = false;
      }
    },

    selectDirBrowserPath() {
      if (!this.dirBrowserPath) return;
      if (this._dirBrowserMode === 'output') {
        this.config.output_dir = this.dirBrowserPath;
      } else {
        this.config.project_folder = this.dirBrowserPath;
      }
      this.showDirBrowser = false;
    },

    // ===== 截图上传 =====
    async handleScreenshotUpload(options) {
      this.screenshotUploading = true;
      try {
        const result = await API.assets.uploadScreenshot(options.file);
        this.config.screenshot_paths.push(result.path);
        this.$message.success('截图已上传');
      } catch (e) {
        this.$message.error('截图上传失败: ' + e.message);
      } finally {
        this.screenshotUploading = false;
      }
    },

    removeScreenshot(i) {
      this.config.screenshot_paths.splice(i, 1);
    },

    // ===== AI 重新生成单个字段 =====
    async regenerateField(field) {
      if (!this.config.project_folder) {
        this.$message.warning('请先配置项目文件夹');
        return;
      }
      if (!this.config.course_topic) {
        this.$message.warning('请先填写课程名称');
        return;
      }
      if (!this.firstStudentId) {
        this.$message.warning('该班级暂无学生，无法进行 AI 生成');
        return;
      }
      this.regeneratingFields = { ...this.regeneratingFields, [field]: true };
      try {
        const meta = await API.projects.scan({ folder: this.config.project_folder });
        const result = await API.ai.regenerate({
          project: meta,
          student_id: this.firstStudentId,
          field: field,
          teacher_observation: this.config.teacher_observation || '',
          knowledge_points: this.sharedContent.knowledge_points,
        });
        // 后端返回 { field, value }
        const value = result.value;
        if (field === 'knowledge_points') {
          this.sharedContent.knowledge_points = value || [];
        } else if (field === 'content_summary') {
          if (value.content_items) this.sharedContent.content_items = value.content_items;
          if (value.ability_improvement) this.sharedContent.ability_improvement = value.ability_improvement;
        } else if (field === 'homework_vocab') {
          if (value.homework) this.sharedContent.homework = value.homework;
          if (value.vocabulary) this.sharedContent.vocabulary = value.vocabulary;
        }
        this.$message.success('重新生成成功');
      } catch (e) {
        this.$message.error('重新生成失败: ' + e.message);
      } finally {
        this.regeneratingFields = { ...this.regeneratingFields, [field]: false };
      }
    },

    // ===== 批量生成 =====
    async batchGenerate() {
      if (!this.config.class_id) {
        this.$message.warning('请选择班级');
        return;
      }
      this.batchRunning = true;
      this.batchProgress = 5;
      this.batchProgressText = '正在生成共享内容...';
      this.batchResults = [];

      try {
        const progressTimer = setInterval(() => {
          if (this.batchProgress < 90) {
            this.batchProgress += Math.floor(Math.random() * 8) + 2;
            if (this.batchProgress > 85) {
              this.batchProgressText = '正在保存报告...';
            }
          }
        }, 2000);

        const result = await API.reports.batchGenerate({
          class_id: this.config.class_id,
          course_date: this.config.course_date,
          course_topic: this.config.course_topic,
          project_folder: this.config.project_folder,
          teacher_observation: this.config.teacher_observation || '',
          template_id: this.config.template_id,
          output_dir: this.config.output_dir || null,
          auto_export: false,
          screenshot_paths: this.config.screenshot_paths,
        });

        clearInterval(progressTimer);
        this.batchProgress = 100;
        this.batchProgressText = '完成';
        this.batchResults = result.results || [];
        this.classInfo = result.class_name || '';

        // 填充共享内容（如果返回了可以填充）
        if (result.results && result.results.length > 0) {
          // 尝试加载已保存记录来填充共享编辑区
          await this.loadSharedFromRecord(result.results[0].record_id);
        }

        if (result.success === result.total) {
          this.$message.success(`🎉 全部 ${result.total} 份报告生成成功`);
        } else {
          this.$message.warning(`生成完成：${result.success} 成功，${result.failed} 失败，可手动编辑评价`);
        }
      } catch (e) {
        this.batchProgress = 0;
        this.batchProgressText = '';
        this.$message.error('批量生成失败: ' + e.message);
      } finally {
        this.batchRunning = false;
      }
    },

    async loadSharedFromRecord(recordId) {
      if (!recordId) return;
      try {
        const record = await API.reports.get(recordId);
        if (record.knowledge_points) this.sharedContent.knowledge_points = record.knowledge_points;
        if (record.ability_improvement) this.sharedContent.ability_improvement = record.ability_improvement;
        if (record.content_items) this.sharedContent.content_items = record.content_items;
        if (record.vocabulary) this.sharedContent.vocabulary = record.vocabulary;
        if (record.homework) this.sharedContent.homework = record.homework;
      } catch (e) {
        console.error('加载共享内容失败:', e);
      }
    },

    // ===== 保存全部记录 =====
    async saveAllRecords() {
      this.savingAll = true;
      this.savingAllCount = 0;
      for (const r of this.batchResults) {
        if (!r.record_id) continue;
        try {
          await API.reports.patch(r.record_id, {
            evaluation: r.evaluation || '',
          });
          r.error = null;
          this.savingAllCount++;
        } catch (e) {
          console.error('保存失败:', r.student_name, e);
        }
      }
      this.$message.success(`已保存 ${this.savingAllCount}/${this.batchResults.length} 份评价`);
      this.savingAll = false;
    },

    // ===== 导出 =====
    async exportSinglePdf(row) {
      if (!row.record_id) return;
      try {
        await API.reports.export(row.record_id, this.config.template_id, null, this.config.output_dir);
        this.$message.success(row.student_name + ' PDF 已导出');
      } catch (e) {
        this.$message.error('导出失败: ' + e.message);
      }
    },

    // ===== 预览 =====
    async previewReport(row) {
      if (!row.record_id) return;
      this.previewRecordId = row.record_id;
      this.showPreviewDialog = true;
      this.previewHtml = '';
      this.previewError = '';
      this.previewLoading = true;
      try {
        const html = await API.reports.preview(row.record_id, this.config.template_id, null, this.config.screenshot_paths);
        this.previewHtml = html;
      } catch (e) {
        this.previewError = '预览生成失败: ' + e.message;
      } finally {
        this.previewLoading = false;
      }
    },

    async exportPdf() {
      const records = this.batchResults.filter(r => !r.error && r.record_id);
      if (records.length === 0) {
        this.$message.warning('没有可导出的记录');
        return;
      }
      this.exporting = true;
      this.$message.info('开始导出 PDF（共 ' + records.length + ' 份）...');
      let count = 0;
      for (const r of records) {
        try {
          await API.reports.export(r.record_id, this.config.template_id, null, this.config.output_dir);
          count++;
        } catch (e) {
          console.error('导出失败:', r.student_name, e);
        }
      }
      this.$message.success(`已完成 ${count}/${records.length} 份 PDF 导出`);
      this.exporting = false;
    },

    async exportWord() {
      const records = this.batchResults.filter(r => !r.error && r.record_id);
      if (records.length === 0) {
        this.$message.warning('没有可导出的记录');
        return;
      }
      this.wordExporting = true;
      this.$message.info('开始导出 Word（共 ' + records.length + ' 份）...');
      let count = 0;
      for (const r of records) {
        try {
          await API.reports.exportWord(r.record_id, this.config.template_id, null, this.config.output_dir);
          count++;
        } catch (e) {
          console.error('导出失败:', r.student_name, e);
        }
      }
      this.$message.success(`已完成 ${count}/${records.length} 份 Word 导出`);
      this.wordExporting = false;
    },
  },
};
