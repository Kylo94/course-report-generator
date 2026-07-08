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
              <el-form-item label="教师观察（全局）">
                <el-input v-model="config.teacher_observation" type="textarea" :rows="2"
                  maxlength="300" show-word-limit
                  placeholder="输入对班级整体的课堂观察，AI 评价将参考此信息" style="width:400px" @blur="autoSaveShared" />
              </el-form-item>
              <el-form-item v-if="studentList.length > 0" label="逐学生观察">
                <div style="width:100%;">
                  <div style="font-size:12px;color:#909399;margin-bottom:8px;">
                    为个别学生填写个性化观察（选填），留空则使用上方全局观察
                  </div>
                  <div v-for="s in studentList" :key="s.id"
                    style="display:flex;align-items:flex-start;gap:8px;margin-bottom:6px;padding:6px 8px;border:1px solid #e4e7ed;border-radius:4px;">
                    <div style="min-width:60px;font-weight:500;padding-top:4px;font-size:13px;">{{ s.name }}</div>
                    <el-input v-model="observations[s.id]" type="textarea" :rows="1"
                      maxlength="200" show-word-limit
                      placeholder="个性化观察（选填）" style="flex:1" />
                  </div>
                </div>
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
              show-word-limit placeholder="输入能力提升" @blur="autoSaveShared" />
          </el-card>

          <!-- 内容概述（AI 生成后才显示） -->
          <el-card v-if="sharedContent.content_items && sharedContent.content_items.length > 0" class="section-card">
            <template #header>
              <span>📝 内容概述</span>
              <el-button size="small" type="warning" link style="float:right"
                :disabled="batchRunning" @click="regenerateField('content_summary')">
                {{ regeneratingFields['content_summary'] ? '生成中...' : '重新生成' }}
              </el-button>
            </template>
            <div v-for="(item, i) in sharedContent.content_items" :key="i" class="content-item">
              <div class="content-item-header">
                {{ item.kp }}
                <el-button size="small" type="danger" link @click="removeContentItem(i)">删除</el-button>
              </div>
              <el-input v-model="item.text" type="textarea" :rows="3"
                maxlength="200" show-word-limit @blur="autoSaveShared" />
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
                <el-input v-model="sharedContent.vocabulary.word" style="width:200px" @blur="autoSaveShared" />
              </el-form-item>
              <el-form-item label="音标">
                <el-input v-model="sharedContent.vocabulary.phonetic" style="width:200px" @blur="autoSaveShared" />
              </el-form-item>
              <el-form-item label="释义">
                <el-input v-model="sharedContent.vocabulary.meaning" style="width:300px" @blur="autoSaveShared" />
              </el-form-item>
              <el-form-item label="例句">
                <el-input v-model="sharedContent.vocabulary.example" type="textarea" :rows="2" style="width:400px" @blur="autoSaveShared" />
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
            <!-- 多题模式 -->
            <div v-if="sharedContent.homework.questions && sharedContent.homework.questions.length > 0">
              <div v-for="(q, qi) in sharedContent.homework.questions" :key="qi"
                style="margin-bottom:16px;padding:12px;border:1px solid #e4e7ed;border-radius:6px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                  <strong>第 {{ qi+1 }} 题</strong>
                  <el-button size="small" type="danger" link @click="removeQuestion(qi)">删除</el-button>
                </div>
                <el-form label-width="80px" size="small">
                  <el-form-item label="题目">
                    <el-input v-model="q.goal" type="textarea" :rows="2" style="width:400px" />
                  </el-form-item>
                  <el-form-item label="提示">
                    <div v-for="(h, hi) in q.hints" :key="'qh'+hi" style="margin-bottom:4px">
                      <el-input v-model="q.hints[hi]" style="width:300px" placeholder="提示内容">
                        <template #prefix>#{{ hi+1 }}</template>
                        <template #suffix>
                          <el-button link type="danger" size="small" @click="removeQuestionHint(qi, hi)">×</el-button>
                        </template>
                      </el-input>
                    </div>
                    <el-button size="small" @click="addQuestionHint(qi)">+ 添加提示</el-button>
                  </el-form-item>
                </el-form>
              </div>
              <el-button size="small" @click="addQuestion">+ 添加题目</el-button>
            </div>
            <!-- 单题兼容模式 -->
            <el-form v-else label-width="100px" size="small">
              <el-form-item label="作业目标">
                <el-input v-model="sharedContent.homework.goal" type="textarea" :rows="2" style="width:400px" @blur="autoSaveShared" />
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
                  <el-button v-if="batchId" size="small" link type="primary"
                    @click="exportSinglePdf(r)">导出PDF</el-button>
                  <el-button v-if="batchId" size="small" link type="info"
                    @click="previewReport(r)">预览</el-button>
                </span>
              </div>
              <el-input v-model="r.evaluation" type="textarea" :rows="3"
                maxlength="500" show-word-limit placeholder="输入该学生评价" />
              <div v-if="r.error" style="margin-top:4px;color:#f56c6c;font-size:12px;">{{ r.error }}</div>
            </div>

          </el-card>
        </div>

        <!-- 右侧：侧边栏 -->
        <div class="editor-sidebar">
          <!-- 操作 + 输出设置 -->
          <el-card class="section-card">
            <template #header>⚙️ 批量操作</template>
            <div style="display:flex;flex-direction:column;gap:8px;">
              <el-checkbox v-model="createVocabulary" style="margin-bottom:4px;">生成单词知识点</el-checkbox>

              <!-- 输出目录设置 -->
              <el-form size="small" label-position="top" style="margin-bottom:4px;">
                <el-form-item label="输出目录">
                  <div style="display:flex;gap:8px;">
                    <el-input v-model="config.output_dir" placeholder="留空使用默认路径" style="flex:1" />
                    <el-button @click="browseOutputDir">📂 浏览</el-button>
                  </div>
                  <div style="margin-top:6px;color:#909399;font-size:12px;">
                    默认路径：<code style="background:#f4f4f5;padding:2px 6px;border-radius:3px;">{{ defaultOutputDir }}</code>
                    <span style="margin-left:12px;">
                      导出会创建：
                      <code style="background:#f4f4f5;padding:2px 6px;border-radius:3px;">{{ outputSubdirHint }}</code>
                    </span>
                  </div>
                </el-form-item>
              </el-form>

              <el-button type="primary" class="btn-feature" @click="batchGenerate" :loading="batchRunning"
                :disabled="!config.class_id">
                🚀 批量生成{{ studentCount > 0 ? '（' + studentCount + '人）' : '' }}
              </el-button>
              <div v-if="batchRunning" style="text-align:center;color:#409eff;font-size:13px;">
                {{ batchProgressText }}
                <el-progress :percentage="batchProgress" :stroke-width="12" style="margin-top:6px;" />
              </div>

              <!-- 生成后的导出保存按钮 -->
              <div v-if="batchResults.length > 0" style="margin-top:8px;display:flex;flex-direction:column;gap:8px;">
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

            <!-- 分类切换 -->
            <el-radio-group v-model="screenshotCategory" size="small" style="margin-bottom:8px;width:100%;display:flex;">
              <el-radio-button value="run" style="flex:1;">🚀 运行/效果</el-radio-button>
              <el-radio-button value="code" style="flex:1;">💻 代码</el-radio-button>
              <el-radio-button value="homework" style="flex:1;">📝 作业</el-radio-button>
              <el-radio-button value="general" style="flex:1;">🖼️ 其他</el-radio-button>
            </el-radio-group>

            <el-upload :http-request="handleScreenshotUpload" list-type="picture-card"
              :show-file-list="false" accept="image/jpeg,image/png,image/webp"
              :disabled="screenshotUploading">
              <el-icon><Plus /></el-icon>
            </el-upload>

            <!-- 运行效果/项目截图 -->
            <div v-if="screenshotCategory === 'run'" class="screenshot-grid">
              <div v-for="(s, i) in config.run_screenshots" :key="'run-'+i" class="screenshot-item">
                <img :src="s" alt="运行截图">
                <el-button class="delete-btn" size="small" circle type="danger"
                  @click="removeScreenshot('run', i)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <div v-if="config.run_screenshots.length === 0" class="empty-category">暂无运行截图</div>
            </div>

            <!-- 代码截图 -->
            <div v-if="screenshotCategory === 'code'" class="screenshot-grid">
              <div v-for="(s, i) in config.code_screenshots" :key="'code-'+i" class="screenshot-item">
                <img :src="s" alt="代码截图">
                <el-button class="delete-btn" size="small" circle type="danger"
                  @click="removeScreenshot('code', i)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <div v-if="config.code_screenshots.length === 0" class="empty-category">暂无代码截图</div>
            </div>

            <!-- 作业截图 -->
            <div v-if="screenshotCategory === 'homework'" class="screenshot-grid">
              <div v-for="(s, i) in config.homework_screenshots" :key="'hw-'+i" class="screenshot-item">
                <img :src="s" alt="作业截图">
                <el-button class="delete-btn" size="small" circle type="danger"
                  @click="removeScreenshot('homework', i)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <div v-if="config.homework_screenshots.length === 0" class="empty-category">暂无作业截图</div>
            </div>

            <!-- 其他截图 -->
            <div v-if="screenshotCategory === 'general'" class="screenshot-grid">
              <div v-for="(s, i) in config.screenshot_paths" :key="'gen-'+i" class="screenshot-item">
                <img :src="s" alt="截图">
                <el-button class="delete-btn" size="small" circle type="danger"
                  @click="removeScreenshot('general', i)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <div v-if="config.screenshot_paths.length === 0" class="empty-category">暂无其他截图</div>
            </div>
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
        homework: { goal: '', hints: [], questions: [] },
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

      // 逐学生观察 { student_id: observation_text }
      observations: {},
      createVocabulary: true,

      config: {
        class_id: null,
        course_date: new Date().toISOString().slice(0, 10),
        course_topic: '',
        project_folder: '',
        teacher_observation: '',
        template_id: 'classic',
        output_dir: '',
        screenshot_paths: [],
        run_screenshots: [],
        code_screenshots: [],
        homework_screenshots: [],
      },
      classList: [],
      templateList: [],
      screenshotUploading: false,
      screenshotCategory: 'code',
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
      batchId: null,  // BatchReport 的 ID（替代逐个 record_id）
      // 预览
      showPreviewDialog: false,
      previewHtml: '',
      previewLoading: false,
      previewError: '',
    };
  },

  computed: {
    defaultOutputDir() {
      return this.config.output_dir || '(留空使用默认)';
    },
    outputSubdirHint() {
      return '{上课日期}_{班级名}/PDF(用于打印)/ 与 IMG(用于发送)/';
    },
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
    // 加载系统设置，预填项目目录 + 输出目录
    await this._loadDefaultProjectDir();
    await this._loadDefaultOutputDir();
    // 检查是否通过 URL 参数加载已有批量报告
    const params = Router.getParams();
    if (params.id) {
      await this.loadExistingBatch(parseInt(params.id));
    }
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
      // 优先使用用户设置的默认模板
      const savedDefault = localStorage.getItem('crg_default_template');
      if (savedDefault && this.templateList.some(t => t.id === savedDefault)) {
        this.config.template_id = savedDefault;
      }
      } catch (e) {
        console.error('加载模板列表失败:', e);
      }
    },

    onClassSelected(classId) {
      this.config.class_id = classId;
      this.batchResults = [];
      this.observations = {};
      this.resetSharedContent();
      this.loadFirstStudentId(classId);
    },

    async loadFirstStudentId(classId) {
      try {
        // 加载较多学生以确保覆盖目标班级的学生
        const result = await API.students.list({ page: 1, page_size: 200 });
        const students = result.items || [];
        this.studentList = students.filter(s => s.class_id === classId);
        this.firstStudentId = this.studentList.length > 0 ? this.studentList[0].id : null;
        // 初始化逐学生观察字典
        this.observations = {};
        for (const s of this.studentList) {
          this.observations[s.id] = '';
        }
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
      this.observations = {};
      this.resetSharedContent();
    },

    resetSharedContent() {
      this.sharedContent = {
        knowledge_points: [],
        ability_improvement: '',
        content_items: [],
        vocabulary: { word: '', phonetic: '', meaning: '', example: '' },
        homework: { goal: '', hints: [], questions: [] },
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

    // ===== 多题模式 =====
    addQuestion() {
      if (!this.sharedContent.homework.questions) this.sharedContent.homework.questions = [];
      this.sharedContent.homework.questions.push({ goal: '', hints: [] });
    },
    removeQuestion(qi) {
      if (!this.sharedContent.homework.questions) return;
      this.sharedContent.homework.questions.splice(qi, 1);
    },
    addQuestionHint(qi) {
      if (!this.sharedContent.homework.questions) return;
      const q = this.sharedContent.homework.questions[qi];
      if (!q) return;
      if (!q.hints) q.hints = [];
      q.hints.push('');
    },
    removeQuestionHint(qi, hi) {
      if (!this.sharedContent.homework.questions) return;
      const q = this.sharedContent.homework.questions[qi];
      if (!q || !q.hints) return;
      q.hints.splice(hi, 1);
    },

    // ===== 从系统设置加载默认项目目录 =====
    async _loadDefaultProjectDir() {
      if (this.config.project_folder) return; // 已有值不覆盖
      try {
        const s = await API.settings.get();
        if (s.default_project_dir) {
          this.config.project_folder = s.default_project_dir;
        }
      } catch (_) { /* 静默失败，不影响主流程 */ }
    },

    async _loadDefaultOutputDir() {
      if (this.config.output_dir) return;
      try {
        const s = await API.settings.get();
        const real = s.custom_output_dir || s.default_project_dir || '';
        if (real) {
          this.config.output_dir = real;
        }
      } catch (_) { /* 静默失败，不影响主流程 */ }
    },

    // ===== 目录浏览器 =====
    async openDirBrowser() {
      this._dirBrowserMode = 'project';
      this.dirBrowserPath = '';
      this.dirBrowserItems = [];
      this.dirBrowserError = null;
      this.showDirBrowser = true;
      // 优先使用输入框当前值，其次 localStorage
      const startPath = this.config.project_folder
        || localStorage.getItem('lastDirBrowserPath')
        || '';
      await this.browseToDir(startPath);
    },

    browseOutputDir() {
      this._dirBrowserMode = 'output';
      this.dirBrowserPath = this.config.output_dir || '';
      this.dirBrowserItems = [];
      this.dirBrowserError = null;
      this.showDirBrowser = true;
      const startPath = this.config.output_dir
        || localStorage.getItem('lastOutputDirBrowserPath')
        || '';
      this.browseToDir(startPath);
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
        // 自动识别项目名称：取路径最后一级作为课程名
        this._autoFillCourseName(this.dirBrowserPath);
        // 自动检测 截图/ 文件夹中的截图并上传
        this._autoUploadScreenshots(this.dirBrowserPath);
      }
      this.showDirBrowser = false;
    },

    _autoFillCourseName(folderPath) {
      if (!folderPath || this.config.course_topic) return;
      let name = folderPath.replace(/\/+$/, '').split(/[/\\]/).pop() || '';
      // 去掉前导序号，如 "1."、"21-24."、"33-36."
      name = name.replace(/^\d+(-?\d+)?[.、]\s*/, '');
      if (name && name.length <= 10) {
        this.config.course_topic = name;
      }
    },

    async _autoUploadScreenshots(folderPath) {
      if (!folderPath) return;
      try {
        const result = await API.projects.scanScreenshots({ folder: folderPath });
        // 从 截图/ 目录扫描：{ run_screenshots, code_screenshots, homework_screenshots, other_screenshots }
        // 分别存储到数组中（不再合并成一个列表）
        this.config.run_screenshots = (result.run_screenshots || []).map(s => s.url);
        this.config.code_screenshots = (result.code_screenshots || []).map(s => s.url);
        this.config.homework_screenshots = (result.homework_screenshots || []).map(s => s.url);
        this.config.screenshot_paths = (result.other_screenshots || []).map(s => s.url);

        const totalShots = this.config.run_screenshots.length + this.config.code_screenshots.length + this.config.homework_screenshots.length + this.config.screenshot_paths.length;
        if (totalShots > 0) {
          this.$message.success(`已扫描到 ${totalShots} 张截图（运行/效果 ${this.config.run_screenshots.length} / 代码 ${this.config.code_screenshots.length} / 作业 ${this.config.homework_screenshots.length} / 其他 ${this.config.screenshot_paths.length}）`);
        }
      } catch (e) {
        console.debug('自动上传截图扫描（可忽略）:', e.message);
      }
    },

    // ===== 截图上传 =====
    async handleScreenshotUpload(options) {
      this.screenshotUploading = true;
      try {
        const result = await API.assets.uploadScreenshot(options.file);
        const cat = this.screenshotCategory;
        if (cat === 'run') {
          this.config.run_screenshots.push(result.path);
        } else if (cat === 'code') {
          this.config.code_screenshots.push(result.path);
        } else if (cat === 'homework') {
          this.config.homework_screenshots.push(result.path);
        } else {
          this.config.screenshot_paths.push(result.path);
        }
        this.$message.success('截图已上传');
      } catch (e) {
        this.$message.error('截图上传失败: ' + e.message);
      } finally {
        this.screenshotUploading = false;
      }
    },

    removeScreenshot(cat, i) {
      if (cat === 'run') {
        this.config.run_screenshots.splice(i, 1);
      } else if (cat === 'code') {
        this.config.code_screenshots.splice(i, 1);
      } else if (cat === 'homework') {
        this.config.homework_screenshots.splice(i, 1);
      } else {
        this.config.screenshot_paths.splice(i, 1);
      }
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

      // 构建用户已填写的内容（AI 以用户为准，不再生成这些字段）
      const existingContent = {};
      if (this.sharedContent.knowledge_points && this.sharedContent.knowledge_points.length > 0) {
        existingContent.knowledge_points = this.sharedContent.knowledge_points;
      }
      if (this.sharedContent.content_items && this.sharedContent.content_items.length > 0) {
        existingContent.content_items = this.sharedContent.content_items;
      }
      if (this.sharedContent.ability_improvement && this.sharedContent.ability_improvement.trim()) {
        existingContent.ability_improvement = this.sharedContent.ability_improvement;
      }
      if (this.sharedContent.homework) {
        const hw = this.sharedContent.homework;
        if (hw.goal || (hw.questions && hw.questions.length > 0)) {
          existingContent.homework = hw;
        }
      }
      if (this.sharedContent.vocabulary && this.sharedContent.vocabulary.word) {
        existingContent.vocabulary = this.sharedContent.vocabulary;
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
          observations: this.observations,
          create_vocabulary: this.createVocabulary,
          template_id: this.config.template_id,
          output_dir: this.config.output_dir || null,
          auto_export: false,
          screenshot_paths: this.config.screenshot_paths,
          run_screenshots: this.config.run_screenshots,
          code_screenshots: this.config.code_screenshots,
          homework_screenshots: this.config.homework_screenshots,
          existing_content: Object.keys(existingContent).length > 0 ? existingContent : null,
        });

        clearInterval(progressTimer);
        this.batchProgress = 100;
        this.batchProgressText = '完成';
        this.batchResults = result.results || [];
        this.batchId = result.batch_id || null;
        this.classInfo = result.class_name || '';

        // 填充共享内容（从 batch 记录加载共享字段）
        if (this.batchId) {
          await this.loadSharedFromBatch(this.batchId);
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

    // ===== 保存全部记录（批量更新 evaluations + 共享内容） =====
    async saveAllRecords() {
      if (!this.batchId) {
        this.$message.warning('没有可保存的批量报告');
        return;
      }
      this.savingAll = true;
      this.savingAllCount = 0;
      try {
        // 构建 evaluations 字典 { student_id: { name, evaluation } }
        const evaluations = {};
        for (const r of this.batchResults) {
          evaluations[r.student_id] = {
            name: r.student_name,
            evaluation: r.evaluation || '',
          };
        }
        // 同时保存共享内容和截图
        const updateData = {
          evaluations,
          knowledge_points: this.sharedContent.knowledge_points,
          ability_improvement: this.sharedContent.ability_improvement,
          content_items: this.sharedContent.content_items,
          homework: this.sharedContent.homework,
          vocabulary: this.sharedContent.vocabulary,
          teacher_observation: this.config.teacher_observation,
          run_screenshots: this.config.run_screenshots,
          code_screenshots: this.config.code_screenshots,
          homework_screenshots: this.config.homework_screenshots,
          screenshot_paths: this.config.screenshot_paths,
        };
        await API.batchReports.update(this.batchId, updateData);
        this.savingAllCount = this.batchResults.length;
        this.$message.success(`已保存全部内容（含共享信息）`);
      } catch (e) {
        this.$message.error('保存失败: ' + e.message);
      } finally {
        this.savingAll = false;
      }
    },

    // ===== 导出前自动保存共享内容 =====
    async autoSaveShared() {
      // 先确保 Vue 的 v-model 更新已处理完毕
      await this.$nextTick();
      if (!this.batchId) return;
      const hwGoal = this.sharedContent.homework?.goal || '(empty)';
      console.log('[autoSaveShared] 准备保存 homework.goal =', hwGoal);
      try {
        await API.batchReports.update(this.batchId, {
          knowledge_points: this.sharedContent.knowledge_points,
          ability_improvement: this.sharedContent.ability_improvement,
          content_items: this.sharedContent.content_items,
          homework: this.sharedContent.homework,
          vocabulary: this.sharedContent.vocabulary,
          teacher_observation: this.config.teacher_observation,
          run_screenshots: this.config.run_screenshots,
          code_screenshots: this.config.code_screenshots,
          homework_screenshots: this.config.homework_screenshots,
          screenshot_paths: this.config.screenshot_paths,
        });
        console.log('[autoSaveShared] 保存成功 homework.goal =', hwGoal);
      } catch (e) {
        console.warn('自动保存共享内容失败:', e);
      }
    },

    // ===== 导出 =====
    async exportSinglePdf(row) {
      if (!this.batchId) return;
      await this.autoSaveShared();
      try {
        await API.batchReports.exportPdf(this.batchId, row.student_id, this.config.template_id, this.config.output_dir, this.config.screenshot_paths, this.config.code_screenshots, this.config.homework_screenshots, this.config.run_screenshots);
        this.$message.success(row.student_name + ' PDF 已导出');
      } catch (e) {
        this.$message.error('导出失败: ' + e.message);
      }
    },

    // ===== 预览 =====
    async previewReport(row) {
      if (!this.batchId) return;
      const beforeGoal = this.sharedContent.homework?.goal || '(empty)';
      console.log('[previewReport] 保存前 sharedContent.homework.goal =', beforeGoal);
      await this.autoSaveShared();
      const afterGoal = this.sharedContent.homework?.goal || '(empty)';
      console.log('[previewReport] 保存后 sharedContent.homework.goal =', afterGoal);
      this.showPreviewDialog = true;
      this.previewHtml = '';
      this.previewError = '';
      this.previewLoading = true;
      try {
        console.log('[previewReport] 开始调用预览 API, batchId=%s studentId=%s', this.batchId, row.student_id);
        const html = await API.batchReports.preview(this.batchId, row.student_id, this.config.template_id, this.config.screenshot_paths, this.config.code_screenshots, this.config.homework_screenshots, this.config.run_screenshots);
        this.previewHtml = html;
      } catch (e) {
        this.previewError = '预览生成失败: ' + e.message;
      } finally {
        this.previewLoading = false;
      }
    },

    async exportPdf() {
      const results = this.batchResults.filter(r => !r.error);
      if (results.length === 0 || !this.batchId) {
        this.$message.warning('没有可导出的记录');
        return;
      }
      await this.autoSaveShared();
      this.exporting = true;
      this.$message.info('开始导出 PDF（共 ' + results.length + ' 份）...');
      let count = 0;
      for (const r of results) {
        try {
          await API.batchReports.exportPdf(this.batchId, r.student_id, this.config.template_id, this.config.output_dir, this.config.screenshot_paths, this.config.code_screenshots, this.config.homework_screenshots, this.config.run_screenshots);
          count++;
        } catch (e) {
          console.error('导出失败:', r.student_name, e);
        }
      }
      this.$message.success(`已完成 ${count}/${results.length} 份 PDF 导出`);
      this.exporting = false;
    },

    async exportWord() {
      const results = this.batchResults.filter(r => !r.error);
      if (results.length === 0 || !this.batchId) {
        this.$message.warning('没有可导出的记录');
        return;
      }
      this.wordExporting = true;
      await this.autoSaveShared();
      this.$message.info('开始导出 Word（共 ' + results.length + ' 份）...');
      let count = 0;
      for (const r of results) {
        try {
          await API.batchReports.exportWord(this.batchId, r.student_id, this.config.template_id, this.config.output_dir, this.config.screenshot_paths, this.config.code_screenshots, this.config.homework_screenshots, this.config.run_screenshots);
          count++;
        } catch (e) {
          console.error('导出失败:', r.student_name, e);
        }
      }
      this.$message.success(`已完成 ${count}/${results.length} 份 Word 导出`);
      this.wordExporting = false;
    },

    // ===== 从批量报告加载共享内容 =====
    async loadSharedFromBatch(batchId) {
      if (!batchId) return;
      try {
        const batch = await API.batchReports.get(batchId);
        if (!batch) return;
        if (batch.knowledge_points && this.sharedContent.knowledge_points.length === 0) {
          this.sharedContent.knowledge_points = batch.knowledge_points;
        }
        if (batch.ability_improvement && !this.sharedContent.ability_improvement.trim()) {
          this.sharedContent.ability_improvement = batch.ability_improvement;
        }
        if (batch.content_items && this.sharedContent.content_items.length === 0) {
          this.sharedContent.content_items = batch.content_items;
        }
        if (batch.vocabulary && !this.sharedContent.vocabulary.word) {
          this.sharedContent.vocabulary = batch.vocabulary;
        }
        if (batch.homework) {
          const curHw = this.sharedContent.homework;
          if (!curHw.goal && (!curHw.questions || curHw.questions.length === 0)) {
            this.sharedContent.homework = batch.homework;
          }
        }
        // 恢复之前保存的 evaluations 到 batchResults
        if (batch.evaluations && this.batchResults.length > 0) {
          for (const r of this.batchResults) {
            const saved = batch.evaluations[String(r.student_id)];
            if (saved && saved.evaluation) {
              r.evaluation = saved.evaluation;
            }
          }
        }
      } catch (e) {
        console.error('加载批量报告共享内容失败:', e);
      }
    },

    // ===== 从草稿管理加载已有批量报告 =====
    async loadExistingBatch(batchId) {
      try {
        const batch = await API.batchReports.get(batchId);
        if (!batch) {
          this.$message.error('批量报告不存在');
          return;
        }
        // 设置班级和基本信息
        this.config.class_id = batch.class_id;
        this.config.course_date = batch.course_date || '';
        this.config.course_topic = batch.course_topic || '';
        this.config.project_folder = batch.project_folder || '';
        this.config.template_id = batch.template_id || 'classic';
        this.config.teacher_observation = batch.teacher_observation || '';
        this.batchId = batch.id;

        // 恢复截图
        if (batch.run_screenshots) this.config.run_screenshots = batch.run_screenshots;
        if (batch.code_screenshots) this.config.code_screenshots = batch.code_screenshots;
        if (batch.homework_screenshots) this.config.homework_screenshots = batch.homework_screenshots;
        if (batch.screenshot_paths) this.config.screenshot_paths = batch.screenshot_paths;

        // 加载班级和学生
        await this.loadFirstStudentId(batch.class_id);

        // 恢复共享内容
        if (batch.knowledge_points) this.sharedContent.knowledge_points = batch.knowledge_points;
        if (batch.ability_improvement) this.sharedContent.ability_improvement = batch.ability_improvement;
        if (batch.content_items) this.sharedContent.content_items = batch.content_items;
        if (batch.vocabulary) {
          if (batch.vocabulary.word) this.sharedContent.vocabulary.word = batch.vocabulary.word;
          if (batch.vocabulary.phonetic) this.sharedContent.vocabulary.phonetic = batch.vocabulary.phonetic;
          if (batch.vocabulary.meaning) this.sharedContent.vocabulary.meaning = batch.vocabulary.meaning;
          if (batch.vocabulary.example) this.sharedContent.vocabulary.example = batch.vocabulary.example;
        }
        if (batch.homework) this.sharedContent.homework = batch.homework;

        // 从 evaluations 恢复 batchResults
        if (batch.evaluations && this.studentList.length > 0) {
          this.batchResults = this.studentList.map(s => {
            const saved = batch.evaluations[String(s.id)] || {};
            return {
              student_id: s.id,
              student_name: s.name,
              evaluation: (saved.evaluation || ''),
              error: null,
            };
          });
        }

        this.$message.success('已加载批量报告');
      } catch (e) {
        this.$message.error('加载批量报告失败: ' + e.message);
      }
    },
  },
};
