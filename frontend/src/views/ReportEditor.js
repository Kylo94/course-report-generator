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
                <div style="display:flex;gap:8px;width:100%;">
                  <el-input v-model="form.project_folder" placeholder="输入项目文件夹绝对路径，或点击📂浏览" style="flex:1" />
                  <el-button @click="openDirBrowser">📂 浏览</el-button>
                </div>
              </el-form-item>
              <el-form-item label="教师观察">
                <el-input v-model="teacherObservation" type="textarea" :rows="2"
                  maxlength="300" show-word-limit
                  placeholder="输入教师对学生的课堂观察（如专注度、互动表现等），AI 评价将参考此信息"
                  @input="markDirty" style="width:400px" />
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 知识点概括 -->
          <el-card class="section-card">
            <template #header>
              <span>🎯 知识点概括（≤5条，每条≤15字）</span>
              <el-button size="small" type="warning" link style="float:right"
                :disabled="aiGenerating || regeneratingFields['knowledge_points']" @click="regenerateField('knowledge_points')">
                {{ regeneratingFields['knowledge_points'] ? '生成中...' : '重新生成' }}
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
                :disabled="aiGenerating || regeneratingFields['ability_improvement']" @click="regenerateField('ability_improvement')">
                {{ regeneratingFields['ability_improvement'] ? '生成中...' : '重新生成' }}
              </el-button>
            </template>
            <el-input v-model="form.ability_improvement" type="textarea" :rows="2"
              show-word-limit placeholder="输入能力提升" @input="markDirty" />
          </el-card>

          <!-- 内容概述 -->
          <el-card class="section-card">
            <template #header>
              <span>📝 内容概述</span>
              <el-button size="small" type="warning" link style="float:right"
                :disabled="aiGenerating || regeneratingFields['content_summary']" @click="regenerateField('content_summary')">
                {{ regeneratingFields['content_summary'] ? '生成中...' : '重新生成' }}
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
                :disabled="aiGenerating || regeneratingFields['homework_vocab']" @click="regenerateField('homework_vocab')">
                {{ regeneratingFields['homework_vocab'] ? '生成中...' : '重新生成' }}
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
                :disabled="aiGenerating || regeneratingFields['homework_vocab']" @click="regenerateField('homework_vocab')">
                {{ regeneratingFields['homework_vocab'] ? '生成中...' : '重新生成' }}
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
              <span>⭐ 学生评价（建议 180-200 字）</span>
              <el-button size="small" type="warning" link style="float:right"
                :disabled="aiGenerating || regeneratingFields['evaluation']" @click="regenerateField('evaluation')">
                {{ regeneratingFields['evaluation'] ? '生成中...' : '重新生成' }}
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
              <el-button type="primary" class="btn-feature" @click="generateAll" :loading="aiGenerating" size="large">
                🤖 一键生成报告
              </el-button>
              <el-button type="primary" @click="saveDraft" :loading="saving">
                💾 保存草稿
              </el-button>
              <el-button type="success" @click="exportPdf" :loading="exporting" :disabled="aiGenerating">
                📄 导出 PDF
              </el-button>
              <div v-if="pdfDownloadUrl" style="margin-top:4px;">
                <el-alert type="success" :closable="false" show-icon>
                  <template #title>
                    PDF 已生成
                    <a :href="pdfDownloadUrl" target="_blank" style="margin-left:8px;font-weight:bold;">下载</a>
                  </template>
                </el-alert>
              </div>
              <el-button type="warning" @click="exportWord" :loading="wordExporting">
                📝 导出 Word
              </el-button>
              <el-button type="info" @click="showImportDialog = true">
                📂 导入 Word
              </el-button>
              <el-button type="danger" plain @click="confirmDeleteRecord">
                🗑️ 删除
              </el-button>
            </div>
          </el-card>

          <!-- 模板选择 -->
          <el-card class="section-card">
            <template #header>🎨 模板选择</template>
            <el-radio-group v-model="selectedTemplate" @change="onTemplateChange">
              <el-radio v-for="t in templateList" :key="t.id" :value="t.id" style="display:block;margin-bottom:6px;">
                {{ t.name }}
              </el-radio>
            </el-radio-group>
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
              <el-form-item label="Logo 边距">
                <div style="display:flex;gap:8px;align-items:center;">
                  <el-slider v-model="form.logo_config.margin" :min="0" :max="20" style="width:100px;"
                    @change="markDirty" />
                  <span style="width:40px;text-align:right;">{{ form.logo_config.margin }}mm</span>
                </div>
              </el-form-item>
              <el-form-item label="显示范围">
                <el-select v-model="form.logo_config.show_on_all_pages" @change="markDirty">
                  <el-option label="全部页面" :value="true" />
                  <el-option label="仅首页" :value="false" />
                </el-select>
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 输出设置 -->
          <el-card class="section-card">
            <template #header>
              <div style="display:flex;align-items:center;gap:6px;">
                <el-icon size="16"><FolderOpened /></el-icon>
                <span>输出设置</span>
              </div>
            </template>
            <el-form size="small" label-position="top">
              <el-form-item label="输出目录">
                <div style="display:flex;gap:8px;">
                  <el-input v-model="outputDir" placeholder="留空使用默认路径" style="flex:1" />
                  <el-button @click="browseOutputDir">📂 浏览</el-button>
                </div>
                <div v-if="outputDir" style="margin-top:4px;color:#909399;font-size:12px;">
                  导出文件将保存至该目录下的日期文件夹中
                </div>
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 布局设置 -->
          <el-card class="section-card">
            <template #header>🎨 布局设置</template>
            <el-collapse v-model="layoutActivePanels" style="--el-collapse-header-bg-color:transparent;">
              <el-collapse-item title="颜色" name="colors">
                <el-form size="small" label-position="top">
                  <el-form-item label="主色">
                    <div style="display:flex;gap:8px;align-items:center;">
                      <el-color-picker v-model="layoutColors.primary_color" @change="onLayoutChange" />
                      <el-input v-model="layoutColors.primary_color" size="small" style="width:100px;"
                        placeholder="#3B7DDD" @input="onLayoutChange" />
                    </div>
                  </el-form-item>
                  <el-form-item label="辅色">
                    <div style="display:flex;gap:8px;align-items:center;">
                      <el-color-picker v-model="layoutColors.secondary_color" @change="onLayoutChange" />
                      <el-input v-model="layoutColors.secondary_color" size="small" style="width:100px;"
                        placeholder="#F5F5F5" @input="onLayoutChange" />
                    </div>
                  </el-form-item>
                  <el-form-item label="背景色">
                    <div style="display:flex;gap:8px;align-items:center;">
                      <el-color-picker v-model="layoutColors.background_color" @change="onLayoutChange" />
                      <el-input v-model="layoutColors.background_color" size="small" style="width:100px;"
                        placeholder="#FFFFFF" @input="onLayoutChange" />
                    </div>
                  </el-form-item>
                </el-form>
              </el-collapse-item>
              <el-collapse-item title="字体" name="fonts">
                <el-form size="small" label-position="top">
                  <el-form-item label="标题字体">
                    <el-select v-model="layoutColors.font_title" placeholder="默认" clearable
                      @change="onLayoutChange" style="width:170px;">
                      <el-option v-for="f in fontOptions" :key="f.value" :label="f.label" :value="f.value" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="正文字体">
                    <el-select v-model="layoutColors.font_body" placeholder="默认" clearable
                      @change="onLayoutChange" style="width:170px;">
                      <el-option v-for="f in fontOptions" :key="f.value" :label="f.label" :value="f.value" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="标题字号">
                    <div style="display:flex;gap:8px;align-items:center;">
                      <el-slider v-model="layoutColors.font_size_title" :min="12" :max="48" style="width:120px;"
                        @change="onLayoutChange" />
                      <span style="width:40px;text-align:right;">{{ layoutColors.font_size_title }}pt</span>
                    </div>
                  </el-form-item>
                  <el-form-item label="正文字号">
                    <div style="display:flex;gap:8px;align-items:center;">
                      <el-slider v-model="layoutColors.font_size_body" :min="8" :max="20" style="width:120px;"
                        @change="onLayoutChange" />
                      <span style="width:40px;text-align:right;">{{ layoutColors.font_size_body }}pt</span>
                    </div>
                  </el-form-item>
                </el-form>
              </el-collapse-item>
              <el-collapse-item title="背景" name="bg">
                <el-form size="small" label-position="top">
                  <el-form-item label="背景图片">
                    <el-upload
                      :http-request="handleBgImageUpload"
                      :show-file-list="false"
                      accept="image/jpeg,image/png,image/webp"
                    >
                      <el-button size="small">📷 上传背景图</el-button>
                    </el-upload>
                    <div v-if="layoutColors.background_image" class="bg-preview" style="margin-top:8px;position:relative;">
                      <img :src="layoutColors.background_image" alt="背景预览"
                        style="max-width:100%;max-height:80px;border-radius:4px;border:1px solid #dcdfe6;">
                      <el-button size="small" circle type="danger"
                        style="position:absolute;top:-6px;right:-6px;"
                        @click="removeBgImage">×</el-button>
                    </div>
                  </el-form-item>
                </el-form>
              </el-collapse-item>
            </el-collapse>
            <div style="margin-top:8px;display:flex;gap:8px;">
              <el-button size="small" @click="openPreviewDialog" :disabled="!recordId">
                👁️ 预览报告
              </el-button>
              <el-button size="small" @click="resetLayout">↩️ 重置</el-button>
            </div>
          </el-card>
        </div>
      </div>

      <!-- 预览弹窗 -->
      <el-dialog v-model="showPreviewDialog" title="报告预览" width="90%" top="2vh"
        :close-on-click-modal="false" @closed="previewHtml = ''">
        <div v-if="previewLoading" style="text-align:center;padding:40px;">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          <p style="margin-top:12px;color:#909399;">正在生成预览...</p>
        </div>
        <div v-else-if="previewError" style="color:#f56c6c;padding:30px;text-align:center;">
          {{ previewError }}
        </div>
        <iframe v-else-if="previewHtml" :srcdoc="previewHtml" style="width:100%;height:75vh;border:1px solid #dcdfe6;border-radius:4px;" />
        <div v-else style="text-align:center;padding:40px;color:#909399;">暂无预览内容</div>
        <template #footer>
          <el-button @click="showPreviewDialog = false">关闭</el-button>
          <el-button type="primary" @click="refreshPreview" :loading="previewLoading">刷新预览</el-button>
        </template>
      </el-dialog>

      <!-- Word 导入预览弹窗 -->
      <el-dialog v-model="showImportDialog" title="Word 文档导入预览" width="600px">
        <div v-if="importPreview">
          <el-alert
            :title="'解析置信度: ' + (importPreview.confidence * 100).toFixed(0) + '%'"
            :type="importPreview.confidence > 0.8 ? 'success' : 'warning'"
            show-icon style="margin-bottom:16px"
          />
          <div v-if="importPreview.unrecognized_sections && importPreview.unrecognized_sections.length > 0">
            <p style="color:#e6a23c;">以下内容未能自动识别：</p>
            <p v-for="(s, i) in importPreview.unrecognized_sections" :key="i">{{ s }}</p>
          </div>
          <p>导入后将填充以下字段：</p>
          <div>
            <el-tag v-for="(v, k) in importPreview.fields" :key="k" style="margin:4px" type="info">
              {{ fieldLabel(k) }}
            </el-tag>
          </div>
        </div>
        <div v-else>
          <el-upload
            :http-request="handleWordImport"
            accept=".docx"
            :show-file-list="false"
          >
            <el-button type="primary">选择 Word 文件</el-button>
          </el-upload>
          <div style="margin-top:12px;color:#909399;font-size:13px;">
            支持的格式：.docx（由本工具导出的 Word 文档）
          </div>
        </div>
        <template #footer>
          <el-button @click="showImportDialog = false; importPreview = null">取消</el-button>
          <el-button type="primary" @click="applyImport" :disabled="!importPreview">
            应用到编辑器
          </el-button>
        </template>
      </el-dialog>

      <!-- 目录浏览器弹窗 -->
      <el-dialog v-model="showDirBrowser" title="📂 浏览文件夹" width="550px">
        <div style="margin-bottom:12px;padding:8px 12px;background:#f5f7fa;border-radius:4px;font-size:13px;word-break:break-all;color:#606266;">
          当前位置：<strong>{{ dirBrowserPath || '（常用目录）' }}</strong>
        </div>
        <div v-if="dirBrowserLoading" style="text-align:center;padding:30px;">
          <el-icon class="is-loading" :size="24"><Loading /></el-icon>
          <p style="margin-top:8px;color:#909399;">加载中...</p>
        </div>
        <div v-else-if="dirBrowserError" style="color:#f56c6c;padding:16px;">
          {{ dirBrowserError }}
        </div>
        <div v-else class="dir-browser-list">
          <div
            v-for="item in dirBrowserItems"
            :key="item.path"
            class="dir-browser-item"
            :class="{ 'is-parent': item.is_parent || item.is_root }"
            @click="browseToDir(item.path)"
          >
            <span>{{ item.name }}</span>
          </div>
          <div v-if="dirBrowserItems.length === 0" style="text-align:center;padding:30px;color:#909399;">
            此目录下没有子文件夹
          </div>
        </div>
        <template #footer>
          <el-button @click="showDirBrowser = false">取消</el-button>
          <el-button type="primary" @click="selectDirBrowserPath(_dirBrowserMode)"
            :disabled="!dirBrowserPath || dirBrowserLoading">
            ✅ 选择此文件夹
          </el-button>
        </template>
      </el-dialog>
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
      wordExporting: false,
      scanning: false,
      saveState: 'idle', // idle / saving / saved
      dirty: false,
      autoSaveTimer: null,

      // Logo 信息
      logoInfo: { exists: false, path: null },

      // 输出路径
      outputDir: '',

      // 教师观察 (transient, 不持久化)
      teacherObservation: '',

      // AI 生成状态
      aiGenerating: false,
      regeneratingFields: {},   // { fieldName: true/false } 逐字段加载
      aiErrors: {},

      // Word 导入
      showImportDialog: false,
      importPreview: null,

      // 目录浏览器
      showDirBrowser: false,
      dirBrowserPath: '',
      dirBrowserItems: [],
      dirBrowserLoading: false,
      dirBrowserError: null,
      _dirBrowserMode: 'project',

      // PDF 导出
      pdfDownloadUrl: '',

      // 模板选择
      selectedTemplate: 'classic',
      templateList: [],

      // 需要重建项目的元信息
      projectMeta: null,

      // 布局设置（用于 UI 双向绑定，独立于 form.layout_config）
      layoutColors: {
        primary_color: null,
        secondary_color: null,
        background_color: null,
        font_title: null,
        font_body: null,
        font_size_title: 24,
        font_size_body: 11,
        background_image: null,
        page_margin_top: null,
        page_margin_bottom: null,
        page_margin_left: null,
        page_margin_right: null,
      },
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
      layoutActivePanels: ['colors', 'fonts'],

      // 预览
      showPreviewDialog: false,
      previewHtml: '',
      previewLoading: false,
      previewError: '',
      previewDebounceTimer: null,
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

    // 加载模板列表
    await this.loadTemplates();

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
        logo_config: { enabled: true, position: 'top-right', size: 'medium', show_on_all_pages: true, margin: 0 },
        layout_config: null,  // 布局设置，存储为 {primary_color, font_title, ...}
        status: 'draft',
        template_id: 'classic_default',
        project_meta: null,
      };
    },

    cleanLayoutConfig(lc) {
      // 只保留非 null 值以减少存储体积
      if (!lc) return null;
      const cleaned = {};
      for (const [k, v] of Object.entries(lc)) {
        if (v !== null && v !== undefined && v !== '') cleaned[k] = v;
      }
      return Object.keys(cleaned).length > 0 ? cleaned : null;
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
        const lc = record.layout_config || {};
        this.form.layout_config = Object.keys(lc).length > 0 ? { ...lc } : null;
        // 同步到 UI layoutColors
        if (this.form.layout_config) {
          Object.assign(this.layoutColors, this.form.layout_config);
        }
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
    // 背景图片操作
    // =====================
    handleBgImageUpload(options) {
      const file = options.file;
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        this.layoutColors.background_image = e.target.result;
        this.onLayoutChange();
        this.$message.success('背景图片已设置');
      };
      reader.onerror = () => {
        this.$message.error('背景图片读取失败');
      };
      reader.readAsDataURL(file);
    },

    removeBgImage() {
      this.layoutColors.background_image = null;
      this.onLayoutChange();
      this.$message.success('背景图片已移除');
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
    // 项目扫描
    // =====================
    async scanProject() {
      if (!this.form.project_folder) {
        this.$message.warning('请先输入项目文件夹路径');
        return;
      }
      this.scanning = true;
      try {
        const meta = await API.projects.scan({ folder: this.form.project_folder });
        this.form.project_meta = meta;
        this.$message.success('项目扫描成功: ' + (meta.course_title || '未识别课程主题'));
        if (!this.form.course_topic && meta.course_title) {
          this.form.course_topic = meta.course_title;
        }
        this.markDirty();
      } catch (e) {
        this.$message.error('项目扫描失败: ' + e.message);
      } finally {
        this.scanning = false;
      }
    },

    // =====================
    // 目录浏览器（通过后端 API 浏览文件系统）
    // =====================
    async openDirBrowser() {
      this._dirBrowserMode = 'project';
      this.showDirBrowser = true;
      this.dirBrowserPath = '';
      this.dirBrowserItems = [];
      this.dirBrowserError = null;
      const lastPath = localStorage.getItem('lastDirBrowserPath');
      await this.browseToDir(lastPath || '');
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

    selectDirBrowserPath(type) {
      if (!this.dirBrowserPath) return;
      if (type === 'output') {
        this.outputDir = this.dirBrowserPath;
        this.$message.success('已选择输出目录: ' + this.dirBrowserPath);
      } else {
        this.form.project_folder = this.dirBrowserPath;
        this.$message.success('已选择文件夹: ' + this.dirBrowserPath);
      }
      this.showDirBrowser = false;
    },

    browseOutputDir() {
      this.showDirBrowser = true;
      this.dirBrowserPath = this.outputDir || '';
      this.dirBrowserItems = [];
      this.dirBrowserError = null;
      this._dirBrowserMode = 'output';
      const lastPath = localStorage.getItem('lastOutputDirBrowserPath');
      this.browseToDir(lastPath || '');
    },

    // =====================
    // AI 重新生成
    // =====================
    async regenerateField(field) {
      if (!this.form.student_id) {
        this.$message.warning('请先选择学生');
        return;
      }

      // 确保 project_meta 完整（如果只有文件夹路径则自动扫描）
      if (!this.form.project_meta || !this.form.project_meta.entry_file) {
        if (this.form.project_folder) {
          this.$message.info('正在扫描项目...');
          try {
            const meta = await API.projects.scan({ folder: this.form.project_folder });
            this.form.project_meta = meta;
            if (!this.form.course_topic && meta.course_title) {
              this.form.course_topic = meta.course_title;
            }
          } catch (e) {
            this.$message.error('项目扫描失败: ' + e.message);
            return;
          }
        } else {
          this.$message.warning('请先设置项目文件夹');
          return;
        }
      }

      const fieldMap = {
        knowledge_points: 'knowledge_points',
        ability_improvement: 'content_summary',
        content_summary: 'content_summary',
        homework_vocab: 'homework_vocab',
        evaluation: 'evaluation',
      };
      const aiField = fieldMap[field] || field;

      this.regeneratingFields = { ...this.regeneratingFields, [field]: true };
      try {
        const result = await API.ai.regenerate({
          project: this.form.project_meta || { folder: this.form.project_folder || '/tmp' },
          student_id: this.form.student_id,
          field: aiField,
          knowledge_points: this.form.knowledge_points,
          teacher_observation: this.teacherObservation || '',
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
      } finally {
        this.regeneratingFields = { ...this.regeneratingFields, [field]: false };
      }
    },

    // =====================
    // 一键生成
    // =====================
    async generateAll() {
      if (!this.form.student_id) {
        this.$message.warning('请先选择学生');
        return;
      }
      if (!this.form.project_meta || !this.form.project_meta.entry_file) {
        if (this.form.project_folder) {
          try {
            const meta = await API.projects.scan({ folder: this.form.project_folder });
            this.form.project_meta = meta;
            if (!this.form.course_topic && meta.course_title) {
              this.form.course_topic = meta.course_title;
            }
          } catch (e) {
            this.$message.error('项目扫描失败: ' + e.message);
            return;
          }
        } else {
          this.$message.warning('请先设置项目文件夹');
          return;
        }
      }
      this.aiGenerating = true;
      try {
        const result = await API.ai.generate({
          project: this.form.project_meta,
          student_id: this.form.student_id,
          teacher_observation: this.teacherObservation || '',
        });
        const content = result.content;
        if (content.knowledge_points) this.form.knowledge_points = content.knowledge_points;
        if (content.ability_improvement) this.form.ability_improvement = content.ability_improvement;
        if (content.content_items) this.form.content_items = content.content_items;
        if (content.homework) this.form.homework = content.homework;
        if (content.vocabulary) this.form.vocabulary = content.vocabulary;
        if (content.evaluation) this.form.evaluation = content.evaluation;
        if (!this.form.course_topic && this.form.project_meta?.course_title) {
          this.form.course_topic = this.form.project_meta.course_title;
        }
        if (result.errors && Object.keys(result.errors).length > 0) {
          this.$message.warning('部分内容生成失败: ' + Object.values(result.errors).join('; '));
        } else {
          this.$message.success('🎉 报告已全部生成');
        }
        this.markDirty();
      } catch (e) {
        this.$message.error('生成失败: ' + e.message);
      } finally {
        this.aiGenerating = false;
      }
    },

    // =====================
    // Word 导出
    // =====================
    async exportWord() {
      if (!this.recordId) {
        this.$message.warning('请先保存草稿');
        return;
      }
      this.wordExporting = true;
      try {
        const layoutConfig = this.cleanLayoutConfig(this.layoutColors);
        const result = await API.reports.exportWord(this.recordId, this.selectedTemplate, layoutConfig, this.outputDir);
        window.open(result.docx_path, '_blank');
        if (result.custom_path) {
          this.$message.success('Word 已保存到: ' + result.custom_path);
        }
        this.$message.success('Word 导出成功');
      } catch (e) {
        this.$message.error('Word 导出失败: ' + e.message);
      } finally {
        this.wordExporting = false;
      }
    },

    // =====================
    // Word 导入
    // =====================
    async handleWordImport(options) {
      try {
        const result = await API.importWord(options.file);
        this.importPreview = result;
      } catch (e) {
        this.$message.error('导入解析失败: ' + e.message);
      }
    },

    applyImport() {
      if (!this.importPreview) return;
      const fields = this.importPreview.fields;
      for (const [key, value] of Object.entries(fields)) {
        if (value !== null && value !== undefined) {
          this.form[key] = value;
        }
      }
      this.showImportDialog = false;
      this.importPreview = null;
      this.markDirty();
      this.$message.success('已应用导入内容');
    },

    fieldLabel(key) {
      const labels = {
        course_topic: '课程名称', course_date: '上课时间',
        knowledge_points: '知识点', ability_improvement: '能力提升',
        content_items: '内容概述', vocabulary: '单词学习',
        homework: '课后作业', evaluation: '学生评价',
      };
      return labels[key] || key;
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
        // 保留 logo_config 以便持久化
        // 清理 layout_config: 只存非 null 键
        payload.layout_config = this.cleanLayoutConfig(this.layoutColors);

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

    async exportPdf() {
      if (!this.recordId) {
        this.$message.warning('请先保存草稿');
        return;
      }
      this.exporting = true;
      this.pdfDownloadUrl = '';
      try {
        // 先保存再导出
        if (this.dirty) {
          await this.saveDraft();
        }
        const layoutConfig = this.cleanLayoutConfig(this.layoutColors);
        const result = await API.reports.export(this.recordId, this.selectedTemplate, layoutConfig, this.outputDir);
        this.form.status = 'finalized';
        this.pdfDownloadUrl = result.pdf_path;
        if (result.custom_path) {
          this.$message.success('PDF 已保存到: ' + result.custom_path);
        }
        this.$message.success('PDF 导出成功！');
      } catch (e) {
        this.$message.error('导出失败: ' + e.message);
      } finally {
        this.exporting = false;
      }
    },

    async loadTemplates() {
      try {
        this.templateList = await API.templates.list();
        if (this.templateList.length > 0 && this.form.template_id) {
          // 尝试匹配已有模板 ID（去除 _default 后缀兼容旧数据）
          const match = this.templateList.find(
            t => t.id === this.form.template_id || t.id === this.form.template_id.replace('_default', '')
          );
          if (match) this.selectedTemplate = match.id;
        }
      } catch (e) {
        console.error('加载模板列表失败:', e);
      }
    },

    async onTemplateChange(val) {
      this.form.template_id = val;
      // 切换模板时加载该模板的默认主题、Logo 和布局设置
      try {
        const config = await API.templates.getConfig(val);
        if (config) {
          const theme = config.theme;
          if (theme) {
            this.layoutColors.primary_color = null;
            this.layoutColors.secondary_color = null;
            this.layoutColors.font_title = null;
            this.layoutColors.font_body = null;
            this.layoutColors.font_size_title = theme.font_size_title || 24;
            this.layoutColors.font_size_body = theme.font_size_body || 11;
            this.layoutColors.background_color = theme.background_color || null;
            this.layoutColors.background_image = theme.background_image || null;
            this.layoutColors.page_margin_top = theme.page_margin_top || null;
            this.layoutColors.page_margin_bottom = theme.page_margin_bottom || null;
            this.layoutColors.page_margin_left = theme.page_margin_left || null;
            this.layoutColors.page_margin_right = theme.page_margin_right || null;
          }
          // 加载模板的 Logo 配置
          if (config.logo_config) {
            if (!this.form.logo_config) {
              this.form.logo_config = {};
            }
            Object.assign(this.form.logo_config, config.logo_config);
          }
        }
      } catch (_) { /* 不阻塞切换 */ }
      this.onLayoutChange();
      this.markDirty();
    },

    // =====================
    // 布局设置
    // =====================
    onLayoutChange() {
      // 同步 layoutColors → form.layout_config
      this.form.layout_config = this.cleanLayoutConfig(this.layoutColors);
      this.markDirty();
      // 去抖预览：不立即刷新，等用户操作停止
      if (this.previewDebounceTimer) clearTimeout(this.previewDebounceTimer);
      this.previewDebounceTimer = setTimeout(() => {
        if (this.showPreviewDialog) this.refreshPreview();
      }, 800);
    },

    async refreshPreview() {
      if (!this.recordId) return;
      this.previewLoading = true;
      this.previewError = '';
      try {
        const ss = this.form && this.form.screenshot_paths;
        const html = await API.reports.preview(this.recordId, this.selectedTemplate, this.cleanLayoutConfig(this.layoutColors), ss);
        this.previewHtml = html;
      } catch (e) {
        this.previewError = '预览生成失败: ' + e.message;
        this.previewHtml = '';
      } finally {
        this.previewLoading = false;
      }
    },

    openPreviewDialog() {
      this.showPreviewDialog = true;
      this.$nextTick(() => this.refreshPreview());
    },

    resetLayout() {
      this.layoutColors = {
        primary_color: null,
        secondary_color: null,
        background_color: null,
        font_title: null,
        font_body: null,
        font_size_title: 24,
        font_size_body: 11,
        background_image: null,
        page_margin_top: null,
        page_margin_bottom: null,
        page_margin_left: null,
        page_margin_right: null,
      };
      this.onLayoutChange();
      this.$message.success('布局已重置为模板默认');
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
          payload.layout_config = this.cleanLayoutConfig(this.layoutColors);
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
