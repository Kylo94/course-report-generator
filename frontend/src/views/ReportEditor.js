/**
 * 报告编辑器主组件
 * 支持新建/编辑草稿、AI 生成内容、截图上传、Logo 管理、自动保存
 */
const ReportEditorView = {
  template: `
    <div>
      <!-- 选择模式（新建时选择学生后再编辑） -->
      <div v-if="mode === 'select'" class="empty-state">
        <h3 style="margin-bottom: 20px;">新建课程报告</h3>
        <el-select
          v-model="selectedStudentId"
          filterable
          placeholder="请选择学生"
          style="width:300px"
          @change="onStudentSelected"
        >
          <el-option
            v-for="s in studentList"
            :key="s.id"
            :label="s.name + (s.grade ? ' (' + s.grade + ')' : '')"
            :value="s.id"
          />
        </el-select>
        <div style="margin-top: 12px;">
          <el-button size="small" @click="loadStudents">刷新学生列表</el-button>
        </div>
      </div>

      <!-- 编辑器主体 -->
      <div v-else-if="mode === 'edit'" class="editor-layout">
        <!-- 左侧：编辑区 -->
        <div class="editor-main">
          <!-- 基本信息 -->
          <el-card class="section-card">
            <template #header>📋 基本信息</template>
            <el-form label-width="100px" size="small">
              <el-form-item label="学生姓名">
                <el-input :model-value="studentName" disabled style="width:200px" />
              </el-form-item>
              <el-form-item label="上课时间">
                <el-date-picker v-model="form.course_date" type="date" placeholder="选择日期"
                  value-format="YYYY-MM-DD" style="width:200px" />
              </el-form-item>
              <el-form-item label="课程名称">
                <el-input v-model="form.course_topic" maxlength="10" show-word-limit style="width:300px"
                  placeholder="≤10 字" @input="markDirty" />
              </el-form-item>
              <el-form-item label="项目文件夹">
                <el-input v-model="form.project_folder" disabled style="width:400px" />
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 知识点概括 -->
          <el-card class="section-card">
            <template #header>
              <span>🎯 知识点概括（≤5条，每条≤15字）</span>
              <el-button size="small" type="warning" link style="float:right"
                @click="regenerateField('knowledge_points')">
                重新生成
              </el-button>
            </template>
            <div class="kp-tags">
              <el-tag
                v-for="(kp, i) in form.knowledge_points"
                :key="i"
                closable
                :disable-transitions="false"
                @close="removeKp(i)"
              >
                {{ kp }}
              </el-tag>
              <el-input
                v-if="kpInputVisible"
                ref="kpInputRef"
                v-model="kpInputValue"
                class="kp-tag-input"
                size="small"
                maxlength="15"
                show-word-limit
                @keyup.enter="confirmKp"
                @blur="confirmKp"
              />
              <el-button
                v-else
                size="small"
                @click="showKpInput"
                :disabled="form.knowledge_points.length >= 5"
              >
                + 添加
              </el-button>
            </div>
          </el-card>

          <!-- 能力提升 -->
          <el-card class="section-card">
            <template #header>
              <span>💪 能力提升</span>
              <el-button size="small" type="warning" link style="float:right"
                @click="regenerateField('ability_improvement')">
                重新生成
              </el-button>
            </template>
            <el-input v-model="form.ability_improvement" type="textarea" :rows="2"
              maxlength="80" show-word-limit placeholder="30-80 字" @input="markDirty" />
          </el-card>

          <!-- 内容概述 -->
          <el-card class="section-card">
            <template #header>
              <span>📝 内容概述</span>
              <el-button size="small" type="warning" link style="float:right"
                @click="regenerateField('content_summary')">
                重新生成
              </el-button>
            </template>
            <div v-if="!form.content_items || form.content_items.length === 0" style="color:#909399;">
              暂无内容，请先通过 AI 生成或手动添加
            </div>
            <div v-for="(item, i) in form.content_items" :key="i" class="content-item">
              <div class="content-item-header">
                {{ item.kp }}
                <el-button size="small" type="danger" link @click="removeContentItem(i)">删除</el-button>
              </div>
              <el-input v-model="item.text" type="textarea" :rows="3"
                maxlength="200" show-word-limit @input="markDirty" />
            </div>
          </el-card>

          <!-- 单词学习 -->
          <el-card class="section-card">
            <template #header>
              <span>📖 单词学习</span>
              <el-button size="small" type="warning" link style="float:right"
                @click="regenerateField('homework_vocab')">
                重新生成
              </el-button>
            </template>
            <el-form label-width="100px" size="small">
              <el-form-item label="单词">
                <el-input v-model="form.vocabulary.word" style="width:200px" @input="markDirty" />
              </el-form-item>
              <el-form-item label="音标">
                <el-input v-model="form.vocabulary.phonetic" style="width:200px" @input="markDirty" />
              </el-form-item>
              <el-form-item label="释义">
                <el-input v-model="form.vocabulary.meaning" style="width:300px" @input="markDirty" />
              </el-form-item>
              <el-form-item label="例句">
                <el-input v-model="form.vocabulary.example" type="textarea" :rows="2" style="width:400px"
                  @input="markDirty" />
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 课后作业 -->
          <el-card class="section-card">
            <template #header>
              <span>📚 课后作业</span>
              <el-button size="small" type="warning" link style="float:right"
                @click="regenerateField('homework_vocab')">
                重新生成
              </el-button>
            </template>
            <el-form label-width="100px" size="small">
              <el-form-item label="作业目标">
                <el-input v-model="form.homework.goal" type="textarea" :rows="2" style="width:400px"
                  @input="markDirty" />
              </el-form-item>
              <el-form-item label="提示">
                <div v-for="(h, i) in form.homework.hints" :key="'h'+i" style="margin-bottom:4px">
                  <el-input v-model="form.homework.hints[i]" style="width:300px" placeholder="提示内容"
                    @input="markDirty">
                    <template #prefix>#{{ i+1 }}</template>
                    <template #suffix>
                      <el-button link type="danger" size="small" @click="removeHint(i)">×</el-button>
                    </template>
                  </el-input>
                </div>
                <el-button size="small" @click="addHint">+ 添加提示</el-button>
              </el-form-item>
              <el-form-item label="评分点">
                <div v-for="(c, i) in form.homework.criteria" :key="'c'+i" style="margin-bottom:4px">
                  <el-input v-model="form.homework.criteria[i]" style="width:300px" placeholder="评分标准"
                    @input="markDirty">
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

          <!-- 学生评价 -->
          <el-card class="section-card">
            <template #header>
              <span>⭐ 学生评价（建议 180-220 字）</span>
              <el-button size="small" type="warning" link style="float:right"
                @click="regenerateField('evaluation')">
                重新生成
              </el-button>
            </template>
            <el-input v-model="form.evaluation" type="textarea" :rows="6"
              maxlength="500" show-word-limit placeholder="口语化评价，覆盖 6 维度（专注力、逻辑理解、动手能力、协作、表达、创意）"
              @input="markDirty" />
          </el-card>
        </div>

        <!-- 右侧：侧边栏 -->
        <div class="editor-sidebar">
          <!-- 状态信息 -->
          <el-card class="section-card">
            <template #header>📊 状态</template>
            <div style="margin-bottom:8px">
              <el-tag :type="statusType" size="small">{{ statusLabel }}</el-tag>
            </div>
            <div class="auto-save-indicator" :class="saveState">
              <el-icon v-if="saveState === 'saving'"><Loading /></el-icon>
              <el-icon v-else><CircleCheck /></el-icon>
              <span>{{ saveText }}</span>
            </div>
          </el-card>

          <!-- 操作按钮 -->
          <el-card class="section-card">
            <template #header>⚙️ 操作</template>
            <div style="display:flex;flex-direction:column;gap:8px;">
              <el-button type="primary" @click="saveDraft" :loading="saving">
                💾 保存草稿
              </el-button>
              <el-button @click="exportFinal" :loading="exporting">
                📄 标记已导出
              </el-button>
              <el-button type="danger" plain @click="confirmDeleteRecord">
                🗑️ 删除
              </el-button>
            </div>
          </el-card>

          <!-- 截图上传 -->
          <el-card class="section-card">
            <template #header>📷 截图上传</template>
            <el-upload
              :http-request="handleScreenshotUpload"
              list-type="picture-card"
              :show-file-list="false"
              accept="image/jpeg,image/png,image/webp"
            >
              <el-icon><Plus /></el-icon>
            </el-upload>
            <div class="screenshot-grid">
              <div v-for="(s, i) in form.screenshot_paths" :key="i" class="screenshot-item">
                <img :src="s" alt="截图">
                <el-button class="delete-btn" size="small" circle type="danger"
                  @click="removeScreenshot(i)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
            </div>
          </el-card>

          <!-- Logo 管理 -->
          <el-card class="section-card">
            <template #header>🖼️ Logo 设置</template>
            <el-form size="small" label-position="top">
              <el-form-item label="Logo 图片">
                <el-upload
                  :http-request="handleLogoUpload"
                  :show-file-list="false"
                  accept="image/jpeg,image/png,image/webp"
                >
                  <el-button size="small">上传 Logo</el-button>
                </el-upload>
                <div v-if="logoInfo.exists" class="logo-preview">
                  <img :src="logoInfo.path" alt="Logo">
                </div>
              </el-form-item>
              <el-form-item label="显示位置">
                <el-select v-model="form.logo_config.position" @change="markDirty">
                  <el-option label="左上" value="top-left" />
                  <el-option label="右上" value="top-right" />
                  <el-option label="居中顶部" value="top-center" />
                  <el-option label="左下" value="bottom-left" />
                  <el-option label="右下" value="bottom-right" />
                  <el-option label="居中底部" value="bottom-center" />
                </el-select>
              </el-form-item>
              <el-form-item label="尺寸">
                <el-select v-model="form.logo_config.size" @change="markDirty">
                  <el-option label="小 (20mm)" value="small" />
                  <el-option label="中 (30mm)" value="medium" />
                  <el-option label="大 (45mm)" value="large" />
                </el-select>
              </el-form-item>
              <el-form-item label="显示范围">
                <el-select v-model="form.logo_config.show_on_all_pages" @change="markDirty">
                  <el-option label="全部页面" :value="true" />
                  <el-option label="仅首页" :value="false" />
                </el-select>
              </el-form-item>
            </el-form>
          </el-card>
        </div>
      </div>
    </div>
  `,

  data() {
    return {
      // 模式：select / edit
      mode: 'select',
      recordId: null,

      // 学生选择
      studentList: [],
      selectedStudentId: null,
      studentName: '',

      // 编辑表单
      form: this.getEmptyForm(),

      // 知识点标签输入
      kpInputVisible: false,
      kpInputValue: '',

      // 保存相关
      saving: false,
      exporting: false,
      saveState: 'idle', // idle / saving / saved
      dirty: false,
      autoSaveTimer: null,

      // Logo 信息
      logoInfo: { exists: false, path: null },

      // AI 生成状态
      aiGenerating: false,
      aiErrors: {},

      // 需要重建项目的元信息
      projectMeta: null,
    };
  },

  computed: {
    statusType() {
      return { draft: 'warning', finalized: 'success', archived: 'info' }[this.form.status] || 'warning';
    },
    statusLabel() {
      return { draft: '草稿', finalized: '已导出', archived: '已归档' }[this.form.status] || '草稿';
    },
    saveText() {
      if (this.saveState === 'saving') return '保存中...';
      if (this.saveState === 'saved') return '已自动保存';
      return '等待编辑...';
    },
  },

  async mounted() {
    this.Router = Router;

    // 检查是否指定了 record_id
    const params = Router.getParams();
    if (params.id) {
      this.recordId = parseInt(params.id);
      await this.loadRecord(this.recordId);
    } else if (window.location.hash.includes('?new')) {
      this.mode = 'select';
      await this.loadStudents();
    }

    // 加载 Logo 信息
    await this.loadLogoInfo();

    // 启动自动保存
    this.startAutoSave();
  },

  beforeUnmount() {
    if (this.autoSaveTimer) {
      clearInterval(this.autoSaveTimer);
    }
  },

  methods: {
    getEmptyForm() {
      return {
        student_id: null,
        course_date: new Date().toISOString().slice(0, 10),
        course_topic: '',
        project_folder: '',
        knowledge_points: [],
        ability_improvement: '',
        content_items: [],
        homework: { goal: '', hints: [], criteria: [] },
        vocabulary: { word: '', phonetic: '', meaning: '', example: '' },
        evaluation: '',
        screenshot_paths: [],
        logo_config: { enabled: true, position: 'top-right', size: 'medium', show_on_all_pages: true },
        status: 'draft',
        template_id: 'classic_default',
        project_meta: null,
      };
    },

    async loadStudents() {
      try {
        const result = await API.students.list({ page_size: 200 });
        this.studentList = result.items;
      } catch (e) {
        this.$message.error('加载学生列表失败: ' + e.message);
      }
    },

    async onStudentSelected(studentId) {
      try {
        const student = await API.students.get(studentId);
        this.studentName = student.name;
        this.form.student_id = studentId;
        this.mode = 'edit';
      } catch (e) {
        this.$message.error('获取学生信息失败: ' + e.message);
      }
    },

    async loadRecord(id) {
      try {
        const record = await API.reports.get(id);
        this.recordId = id;
        this.mode = 'edit';
        this.form.student_id = record.student_id;

        // 填充表单
        this.form.course_date = record.course_date || new Date().toISOString().slice(0, 10);
        this.form.course_topic = record.course_topic || '';
        this.form.project_folder = record.project_folder || '';
        this.form.knowledge_points = record.knowledge_points || [];
        this.form.ability_improvement = record.ability_improvement || '';
        this.form.content_items = record.content_items || [];
        this.form.homework = record.homework || { goal: '', hints: [], criteria: [] };
        this.form.vocabulary = record.vocabulary || { word: '', phonetic: '', meaning: '', example: '' };
        this.form.evaluation = record.evaluation || '';
        this.form.screenshot_paths = record.screenshot_paths || [];
        this.form.logo_config = { ...this.form.logo_config, ...(record.logo_config || {}) };
        this.form.status = record.status || 'draft';
        this.form.template_id = record.template_id || 'classic_default';
        this.form.project_meta = record.project_meta;

        // 获取学生名
        if (record.student_id) {
          try {
            const student = await API.students.get(record.student_id);
            this.studentName = student.name;
          } catch (_) { /* ignore */ }
        }
      } catch (e) {
        this.$message.error('加载记录失败: ' + e.message);
      }
    },

    // =====================
    // 知识点标签操作
    // =====================
    showKpInput() {
      this.kpInputVisible = true;
      this.$nextTick(() => {
        if (this.$refs.kpInputRef) this.$refs.kpInputRef.focus();
      });
    },

    confirmKp() {
      const val = this.kpInputValue.trim();
      if (val && this.form.knowledge_points.length < 5) {
        this.form.knowledge_points.push(val);
        this.markDirty();
      }
      this.kpInputVisible = false;
      this.kpInputValue = '';
    },

    removeKp(i) {
      this.form.knowledge_points.splice(i, 1);
      this.markDirty();
    },

    removeContentItem(i) {
      this.form.content_items.splice(i, 1);
      this.markDirty();
    },

    addHint() {
      this.form.homework.hints.push('');
      this.markDirty();
    },

    removeHint(i) {
      this.form.homework.hints.splice(i, 1);
      this.markDirty();
    },

    addCriterion() {
      this.form.homework.criteria.push('');
      this.markDirty();
    },

    removeCriterion(i) {
      this.form.homework.criteria.splice(i, 1);
      this.markDirty();
    },

    // =====================
    // 截图操作
    // =====================
    async handleScreenshotUpload(options) {
      try {
        const result = await API.assets.uploadScreenshot(options.file);
        this.form.screenshot_paths.push(result.path);
        this.markDirty();
        this.$message.success('截图已上传');
      } catch (e) {
        this.$message.error('上传失败: ' + e.message);
      }
    },

    removeScreenshot(i) {
      this.form.screenshot_paths.splice(i, 1);
      this.markDirty();
    },

    // =====================
    // Logo 操作
    // =====================
    async handleLogoUpload(options) {
      try {
        await API.assets.uploadLogo(options.file);
        await this.loadLogoInfo();
        this.markDirty();
        this.$message.success('Logo 已上传');
      } catch (e) {
        this.$message.error('上传失败: ' + e.message);
      }
    },

    async loadLogoInfo() {
      try {
        this.logoInfo = await API.assets.getLogo();
      } catch (_) { /* ignore */ }
    },

    // =====================
    // AI 重新生成
    // =====================
    async regenerateField(field) {
      if (!this.form.student_id) {
        this.$message.warning('请先选择学生');
        return;
      }

      const fieldMap = {
        knowledge_points: 'knowledge_points',
        ability_improvement: 'content_summary',
        content_summary: 'content_summary',
        homework_vocab: 'homework_vocab',
        evaluation: 'evaluation',
      };
      const aiField = fieldMap[field] || field;

      try {
        const result = await API.ai.regenerate({
          project: this.form.project_meta || { folder: this.form.project_folder || '/tmp' },
          student_id: this.form.student_id,
          field: aiField,
          knowledge_points: this.form.knowledge_points,
          teacher_observation: '',
        });

        if (field === 'knowledge_points') {
          this.form.knowledge_points = result.value;
        } else if (field === 'ability_improvement' || field === 'content_summary') {
          if (result.value.content_items) {
            this.form.content_items = result.value.content_items;
          }
          if (result.value.ability_improvement) {
            this.form.ability_improvement = result.value.ability_improvement;
          }
        } else if (field === 'homework_vocab') {
          if (result.value.homework) this.form.homework = result.value.homework;
          if (result.value.vocabulary) this.form.vocabulary = result.value.vocabulary;
        } else if (field === 'evaluation') {
          this.form.evaluation = result.value;
        }
        this.markDirty();
        this.$message.success('重新生成成功');
      } catch (e) {
        this.$message.error('重新生成失败: ' + e.message);
      }
    },

    // =====================
    // 保存操作
    // =====================
    markDirty() {
      this.dirty = true;
      this.saveState = 'idle';
    },

    async saveDraft() {
      this.saving = true;
      try {
        const payload = { ...this.form };
        delete payload.project_meta;
        delete payload.logo_config;

        if (this.recordId) {
          await API.reports.patch(this.recordId, payload);
        } else {
          const result = await API.reports.create({
            ...payload,
            student_id: this.form.student_id,
          });
          this.recordId = result.id;
          // 更新 URL hash
          window.location.hash = '#editor?id=' + result.id;
        }
        this.dirty = false;
        this.saveState = 'saved';
        this.$message.success('已保存');
      } catch (e) {
        this.$message.error('保存失败: ' + e.message);
      } finally {
        this.saving = false;
      }
    },

    async exportFinal() {
      if (!this.recordId) {
        this.$message.warning('请先保存草稿');
        return;
      }
      this.exporting = true;
      try {
        await API.reports.updateStatus(this.recordId, 'finalized');
        this.form.status = 'finalized';
        this.$message.success('已标记为已导出');
      } catch (e) {
        this.$message.error('操作失败: ' + e.message);
      } finally {
        this.exporting = false;
      }
    },

    confirmDeleteRecord() {
      if (!this.recordId) {
        this.$message.warning('无记录可删除');
        return;
      }
      this.$confirm('确定删除此记录？', '确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      }).then(async () => {
        try {
          await API.reports.delete(this.recordId);
          this.$message.success('已删除');
          Router.navigate('dashboard');
        } catch (e) {
          this.$message.error('删除失败: ' + e.message);
        }
      }).catch(() => {});
    },

    // =====================
    // 自动保存
    // =====================
    startAutoSave() {
      this.autoSaveTimer = setInterval(async () => {
        if (!this.dirty || !this.recordId) return;

        this.saveState = 'saving';
        try {
          const payload = { ...this.form };
          delete payload.project_meta;
          delete payload.logo_config;
          await API.reports.patch(this.recordId, payload);
          this.dirty = false;
          this.saveState = 'saved';
        } catch (e) {
          console.error('自动保存失败:', e);
          this.saveState = 'idle';
        }
      }, 30000);
    },
  },
};
