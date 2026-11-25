/**
 * 草稿管理列表页面
 * 展示 CourseRecord（个人报告）和 BatchReport（批量报告）
 */
const DraftListView = {
  template: `
    <div>
      <h2 style="margin-bottom: 16px;">📄 草稿管理</h2>

      <!-- 筛选栏 -->
      <el-card style="margin-bottom: 16px;">
        <el-form :inline="true" :model="filters" size="default" label-width="76px">
          <el-form-item label="班级">
            <el-select v-model="filters.class_id" placeholder="全部班级" clearable style="width:150px"
              @change="search">
              <el-option v-for="c in classList" :key="c.id"
                :label="c.name" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="filters.status" placeholder="全部" clearable style="width:120px">
              <el-option label="草稿" value="draft" />
              <el-option label="已导出" value="finalized" />
              <el-option label="已归档" value="archived" />
            </el-select>
          </el-form-item>
          <el-form-item label="模板">
            <el-select v-model="filters.template_id" placeholder="全部" clearable style="width:140px">
              <el-option v-for="t in templateList" :key="t.id"
                :label="t.name" :value="t.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="课程名">
            <el-input v-model="filters.keyword" placeholder="搜索课程/班级" clearable style="width:200px" />
          </el-form-item>
          <el-form-item label="上课日期">
            <el-date-picker
              v-model="filters.dateRange" type="daterange" range-separator="至"
              start-placeholder="起" end-placeholder="止"
              value-format="YYYY-MM-DD" style="width:240px" />
          </el-form-item>
          <el-form-item>
            <div class="btn-group">
              <el-button type="primary" @click="search">查询</el-button>
              <el-button @click="resetFilters">重置</el-button>
            </div>
          </el-form-item>
        </el-form>
        <!-- 排序条 -->
        <div class="sort-bar">
          <span class="sort-bar-label">排序：</span>
          <el-radio-group v-model="sortBy" size="small" @change="onSortChange">
            <el-radio-button value="updated_at">最后修改</el-radio-button>
            <el-radio-button value="created_at">创建时间</el-radio-button>
            <el-radio-button value="course_date">上课日期</el-radio-button>
            <el-radio-button value="student_count">学生数</el-radio-button>
          </el-radio-group>
          <el-button size="small" link class="sort-dir-btn" @click="toggleSortDir">
            <el-icon><component :is="sortDir === 'desc' ? 'SortDown' : 'SortUp'" /></el-icon>
            {{ sortDir === 'desc' ? '降序' : '升序' }}
          </el-button>
        </div>
      </el-card>

      <!-- 数据表格 -->
      <el-card>
        <div v-if="loading" style="text-align:center;padding:40px">
          <el-icon class="is-loading" :size="24"><Loading /></el-icon>
          <p>加载中...</p>
        </div>
        <div v-else-if="items.length === 0" class="empty-state">
          <el-icon><FolderDelete /></el-icon>
          <p>暂无记录</p>
        </div>
        <template v-else>
          <!-- 批量操作栏 -->
          <div style="margin-bottom:12px;display:flex;align-items:center;gap:12px;">
            <el-checkbox v-model="selectAll" :indeterminate="isIndeterminate" @change="onSelectAllChange">
              全选
            </el-checkbox>
            <span style="color:#909399;font-size:13px;">已选 {{ selectedIds.length }} 项</span>
            <el-button
              size="small" type="primary" :disabled="!canBatchExport"
              @click="showBatchExportDialog"
              :loading="batchExporting"
            >
              📤 导出报告
            </el-button>
            <el-button
              size="small" type="danger" :disabled="selectedIds.length === 0"
              @click="confirmBatchDelete"
              :loading="batchDeleting"
            >
              批量删除
            </el-button>
            <span v-if="selectedRecordIds.length > 0 && selectedBatchIds.length > 0"
              style="color:#E6A23C;font-size:12px;">
              提示：导出报告仅支持「批量报告」，个人报告请单独操作
            </span>
          </div>
          <el-table
            ref="tableRef"
            :data="items" stripe style="width:100%"
            @selection-change="onSelectionChange"
            row-key="rowKey"
          >
            <el-table-column type="selection" width="40" />
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="course_topic" label="课程名称" min-width="160" />
          <el-table-column label="班级" width="120">
            <template #default="{ row }">
              <span v-if="row._type === 'batch'">{{ row.class_name || '-' }}</span>
              <span v-else style="color:#909399;">-</span>
            </template>
          </el-table-column>
          <el-table-column label="模板" width="100">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ templateName(row.template_id) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="学生数" width="80" sortable :sort-orders="['descending','ascending']">
            <template #default="{ row }">
              <span>{{ row.student_count ?? 0 }}</span>
              <el-icon v-if="row.showcase_count > 0" title="已上传展示图"
                style="margin-left:4px;color:#e6a23c;vertical-align:middle;"><Picture /></el-icon>
            </template>
          </el-table-column>
          <el-table-column label="课程日期" width="120" prop="course_date" sortable
            :sort-orders="['descending','ascending']" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最后修改" width="170" prop="updated_at" sortable
            :sort-orders="['descending','ascending']">
            <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <div class="draft-actions">
                <el-button size="small" type="primary" link @click="openDraft(row)">
                  编辑
                </el-button>
                <el-button
                  v-if="row.status === 'draft'"
                  size="small" type="success" link @click="finalizeDraft(row)"
                >
                  标记已导出
                </el-button>
                <el-button size="small" type="danger" link @click="confirmDelete(row)">
                  删除
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
          </template>

        <!-- 分页 -->
        <div style="margin-top:16px;text-align:right;">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            @current-change="loadList"
            @size-change="loadList"
          />
        </div>
      </el-card>
    </div>

    <!-- PR2: 批量导出弹窗 -->
    <el-dialog
      v-model="batchExportDialog"
      title="📤 导出报告"
      width="640px"
      :close-on-click-modal="false"
      @close="onBatchExportDialogClose"
    >
      <div v-if="batchStudentsLoading" style="text-align:center;padding:24px;">
        <el-icon class="is-loading"><Loading /></el-icon>
        加载学生列表中...
      </div>
      <template v-else-if="selectedBatchItems.length > 0">
        <el-form label-width="100px" size="small">
          <el-form-item label="已选批量报告">
            <div style="line-height:1.8;">
              <div v-for="b in selectedBatchItems" :key="b.id" style="margin-bottom:4px;">
                <el-tag size="small" type="success">#{{ b.id }}</el-tag>
                <strong style="margin-left:6px;">{{ b.course_topic || '(无课程名)' }}</strong>
                <span style="color:#909399;margin-left:6px;">
                  {{ b.class_name || '-' }} · {{ b.course_date || '-' }} · {{ b.student_count || 0 }} 人
                </span>
              </div>
            </div>
          </el-form-item>

          <el-form-item label="学生选择">
            <div
              v-for="b in selectedBatchItems"
              :key="'stu-' + b.id"
              style="margin-bottom:8px;padding:8px;border:1px solid #ebeef5;border-radius:4px;"
            >
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                <strong>#{{ b.id }} {{ b.course_topic || '' }}</strong>
                <el-button
                  size="small" type="text"
                  @click="selectAllStudentsInBatch(b.id)"
                >全选</el-button>
                <el-button
                  size="small" type="text"
                  @click="deselectAllStudentsInBatch(b.id)"
                >清空</el-button>
                <span style="color:#909399;font-size:12px;">
                  已选 {{ (batchStudentSelection[b.id] || []).length }} / {{ (batchStudents[b.id] || []).length }}
                </span>
              </div>
              <el-checkbox-group v-model="batchStudentSelection[b.id]">
                <el-checkbox
                  v-for="s in (batchStudents[b.id] || [])"
                  :key="s.id"
                  :value="s.id"
                >{{ s.name }}</el-checkbox>
              </el-checkbox-group>
              <div v-if="(batchStudents[b.id] || []).length === 0" style="color:#909399;font-size:12px;">
                该批量报告暂无学生
              </div>
            </div>
          </el-form-item>

        </el-form>

        <!-- 导出结果展示 -->
        <div v-if="batchExportResults" style="margin-top:12px;padding:12px;border:1px solid #ebeef5;border-radius:4px;">
          <div style="margin-bottom:8px;">
            <el-tag type="success" size="small">成功 {{ batchExportResults.success }}</el-tag>
            <el-tag v-if="batchExportResults.failed > 0" type="danger" size="small" style="margin-left:6px;">
              失败 {{ batchExportResults.failed }}
            </el-tag>
          </div>
          <div v-if="batchExportResults.results.length > 0" style="max-height:180px;overflow:auto;font-size:12px;">
            <div v-for="r in batchExportResults.results" :key="r.batch_id + '-' + r.student_id" style="padding:2px 0;">
              <span style="color:#67C23A;">✓</span>
              #{{ r.batch_id }} {{ r.name }}
              <a v-if="r.pdf_path" :href="r.pdf_path" target="_blank" style="margin-left:6px;">PDF</a>
              <a v-if="r.docx_path" :href="r.docx_path" target="_blank" style="margin-left:6px;">Word</a>
              <span v-if="r.custom_path" style="color:#909399;margin-left:6px;">已存 {{ r.custom_path }}</span>
            </div>
          </div>
          <div v-if="batchExportResults.errors.length > 0" style="max-height:120px;overflow:auto;font-size:12px;margin-top:6px;">
            <div v-for="(e, idx) in batchExportResults.errors" :key="'err-' + idx" style="color:#F56C6C;padding:2px 0;">
              ✗ #{{ e.batch_id }} 学生{{ e.student_id || '-' }}: {{ e.error }}
            </div>
          </div>
        </div>
      </template>

      <template #footer>
        <el-button @click="batchExportDialog = false">关闭</el-button>
        <el-button
          v-if="!batchExportResults"
          type="primary" :loading="batchExporting"
          :disabled="totalSelectedStudents === 0"
          @click="executeBatchExport"
        >
          开始导出报告（合计 {{ totalSelectedStudents }} 份）
        </el-button>
      </template>
    </el-dialog>
  `,

  data() {
    return {
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      filters: { class_id: null, status: '', keyword: '', template_id: '', dateRange: [] },
      sortBy: 'updated_at',
      sortDir: 'desc',
      templateList: [],
      selectedIds: [],
      selectAll: false,
      isIndeterminate: false,
      batchDeleting: false,
      classList: [],
      // PR2: 报告中心批量导出
      batchExportDialog: false,
      batchExporting: false,
      batchExportResults: null,  // {success, failed, results, errors}
      // 每个选中批量报告的学生列表（弹窗内多选用）
      // 结构: {batchId: [{id, name}], ...}
      batchStudents: {},
      batchStudentsLoading: false,
      // 弹窗里每个批量报告勾选了哪些学生
      // 结构: {batchId: [student_id, ...]}
      batchStudentSelection: {},
    };
  },

  computed: {
    /** 仅批量报告 ID（用于批量导出） */
    selectedBatchIds() {
      return this.selectedIds.filter(s => s.type === 'batch').map(s => s.id);
    },
    /** 仅个人报告 ID（批量导出暂不支持） */
    selectedRecordIds() {
      return this.selectedIds.filter(s => s.type === 'record').map(s => s.id);
    },
    /** 是否可启用"批量导出"：至少选 1 个批量报告，且不混着个人报告 */
    canBatchExport() {
      return this.selectedBatchIds.length >= 1 && this.selectedRecordIds.length === 0;
    },
    /** 弹窗里展示的批量报告条目（带 class_name / topic / date）。
     *  用 items 里的详情补全；若选中项已不在当前页（跨页勾选），
     *  仍保留只带 id 的占位对象，让弹窗不会空白。 */
    selectedBatchItems() {
      const map = new Map(this.items.map(it => [it.rowKey, it]));
      return this.selectedIds
        .filter(s => s.type === 'batch')
        .map(s => map.get(s.rowKey) || { id: s.id, course_topic: '（请回到对应页查看详情）' });
    },
    /** 弹窗里所有批量报告合计选了的学生数 */
    totalSelectedStudents() {
      return Object.values(this.batchStudentSelection)
        .reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0);
    },
  },

  mounted() {
    this.loadClassList();
    this.loadTemplateList();
    this.loadList();
  },

  methods: {
    async loadClassList() {
      try {
        const result = await API.classes.list();
        this.classList = result.items || [];
      } catch (e) {
        console.warn('加载班级列表失败:', e);
      }
    },

    async loadList() {
      this.loading = true;
      try {
        const params = {
          page: this.page,
          page_size: this.pageSize,
          sort_by: this.sortBy,
          sort_dir: this.sortDir,
        };
        if (this.filters.class_id) params.class_id = this.filters.class_id;
        if (this.filters.status) params.status = this.filters.status;
        if (this.filters.keyword) params.keyword = this.filters.keyword;
        if (this.filters.template_id) params.template_id = this.filters.template_id;
        if (this.filters.dateRange && this.filters.dateRange.length === 2) {
          params.date_from = this.filters.dateRange[0];
          params.date_to = this.filters.dateRange[1];
        }

        // —— 统一接口：后端合并个人报告 + 批量报告，全局排序分页 ——
        const result = await API.reports.drafts(params);

        this.items = result.items || [];
        this.total = result.total || this.items.length;
      } catch (e) {
        this.$message.error('加载失败: ' + e.message);
      } finally {
        this.loading = false;
      }
    },

    search() {
      this.page = 1;
      this.loadList();
    },

    resetFilters() {
      this.filters = { class_id: null, status: '', keyword: '', template_id: '', dateRange: [] };
      this.sortBy = 'updated_at';
      this.sortDir = 'desc';
      this.page = 1;
      this.loadList();
    },

    onSortChange() {
      this.page = 1;
      this.loadList();
    },

    toggleSortDir() {
      this.sortDir = this.sortDir === 'desc' ? 'asc' : 'desc';
      this.page = 1;
      this.loadList();
    },

    templateName(id) {
      const t = this.templateList.find(x => x.id === id);
      return t ? t.name : (id || '-');
    },

    async loadTemplateList() {
      try {
        this.templateList = await API.templates.list();
      } catch (e) {
        console.error('加载模板列表失败:', e);
      }
    },

    onSelectionChange(selection) {
      this.selectedIds = selection.map(r => ({ id: r.id, type: r._type, rowKey: r.rowKey }));
      this.selectAll = selection.length === this.items.length && this.items.length > 0;
      this.isIndeterminate = selection.length > 0 && selection.length < this.items.length;
    },

    onSelectAllChange(val) {
      if (this.$refs.tableRef) {
        this.$refs.tableRef.clearSelection();
        if (val) {
          this.$nextTick(() => {
            this.items.forEach(r => this.$refs.tableRef.toggleRowSelection(r, true));
          });
        }
      }
    },

    confirmBatchDelete() {
      const count = this.selectedIds.length;
      this.$confirm(`确定删除选中的 ${count} 条记录？此操作不可撤销。`, '批量删除', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      }).then(async () => {
        this.batchDeleting = true;
        try {
          // 按类型分开删除
          const recordIds = this.selectedIds.filter(s => s.type === 'record').map(s => s.id);
          const batchIds = this.selectedIds.filter(s => s.type === 'batch').map(s => s.id);
          let deleted = 0;
          if (recordIds.length > 0) {
            const res = await API.reports.batchDelete(recordIds);
            deleted += res.deleted || 0;
          }
          if (batchIds.length > 0) {
            const res = await API.batchReports.batchDelete(batchIds);
            deleted += res.deleted || 0;
          }
          this.$message.success(`成功删除 ${deleted} 条记录`);
          this.selectedIds = [];
          this.selectAll = false;
          this.isIndeterminate = false;
          this.loadList();
        } catch (e) {
          this.$message.error('批量删除失败: ' + e.message);
        } finally {
          this.batchDeleting = false;
        }
      }).catch(() => {});
    },

    openDraft(row) {
      if (row._type === 'batch') {
        // 批量报告 → 跳转到报告工作台，带上 batch_id
        window.location.hash = '#batch?id=' + row.id;
      } else {
        // 个人报告编辑已下线，统一引导至报告工作台
        this.$message.info('个人报告编辑已下线，请使用「报告工作台」生成报告');
        this.Router.navigate('batch');
      }
    },

    async finalizeDraft(row) {
      try {
        if (row._type === 'batch') {
          await API.batchReports.updateStatus(row.id, 'finalized');
        } else {
          await API.reports.updateStatus(row.id, 'finalized');
        }
        this.$message.success('已标记为已导出');
        this.loadList();
      } catch (e) {
        this.$message.error('操作失败: ' + e.message);
      }
    },

    confirmDelete(row) {
      this.$confirm('确定删除此记录？此操作不可撤销。', '确认删除', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      }).then(async () => {
        try {
          if (row._type === 'batch') {
            await API.batchReports.delete(row.id);
          } else {
            await API.reports.delete(row.id);
          }
          this.$message.success('已删除');
          this.loadList();
        } catch (e) {
          this.$message.error('删除失败: ' + e.message);
        }
      }).catch(() => {});
    },

    statusType(s) {
      return { draft: 'warning', finalized: 'success', archived: 'info' }[s] || 'info';
    },

    statusLabel(s) {
      return { draft: '草稿', finalized: '已导出', archived: '已归档' }[s] || s;
    },

    formatDate(d) {
      if (!d) return '-';
      return new Date(d).toLocaleString('zh-CN');
    },

    // =========================
    // PR2: 报告中心批量导出
    // =========================
    async showBatchExportDialog() {
      this.batchExportDialog = true;
      this.batchExportResults = null;
      this.batchStudents = {};
      this.batchStudentSelection = {};
      await this.loadBatchStudents();
    },

    async loadBatchStudents() {
      if (this.selectedBatchIds.length === 0) return;
      this.batchStudentsLoading = true;
      try {
        // 并行拉取每个批量报告的详情，从 evaluations JSON 抽学生
        const results = await Promise.allSettled(
          this.selectedBatchIds.map(id => API.batchReports.get(id))
        );
        for (let i = 0; i < this.selectedBatchIds.length; i++) {
          const batchId = this.selectedBatchIds[i];
          const r = results[i];
          if (r.status !== 'fulfilled' || !r.value) {
            this.batchStudents[batchId] = [];
            this.batchStudentSelection[batchId] = [];
            continue;
          }
          const detail = r.value;
          const evals = detail.evaluations || {};
          // 兼容 evaluations 是 dict 的情况（{sid: {name, evaluation}}）
          // 以及 list 的情况（[{student_id, name, evaluation}]）
          let students = [];
          if (Array.isArray(evals)) {
            students = evals.map(e => ({ id: e.student_id, name: e.name })).filter(s => s.id);
          } else if (typeof evals === 'object' && evals !== null) {
            students = Object.entries(evals)
              .map(([sid, v]) => ({
                id: Number(sid),
                name: (v && typeof v === 'object' && v.name) || `学生${sid}`,
              }))
              .filter(s => s.id);
          }
          this.batchStudents[batchId] = students;
          // 默认全选
          this.batchStudentSelection[batchId] = students.map(s => s.id);
        }
      } catch (e) {
        console.error('加载学生列表失败', e);
        this.$message.error('加载学生列表失败: ' + e.message);
      } finally {
        this.batchStudentsLoading = false;
      }
    },

    selectAllStudentsInBatch(batchId) {
      const all = (this.batchStudents[batchId] || []).map(s => s.id);
      this.batchStudentSelection[batchId] = [...all];
    },

    deselectAllStudentsInBatch(batchId) {
      this.batchStudentSelection[batchId] = [];
    },

    async executeBatchExport() {
      if (this.totalSelectedStudents === 0) {
        this.$message.warning('请至少选择 1 名学生');
        return;
      }
      this.batchExporting = true;
      try {
        const items = this.selectedBatchIds
          .filter(bid => (this.batchStudentSelection[bid] || []).length > 0)
          .map(bid => ({
            batch_id: bid,
            student_ids: this.batchStudentSelection[bid],
          }));
        if (items.length === 0) {
          this.$message.warning('请至少选择 1 名学生');
          return;
        }
        const result = await API.batchReports.exportMulti(items, 'both');
        this.batchExportResults = result;
        if (result.failed === 0) {
          this.$message.success(`成功导出 ${result.success} 份报告`);
        } else if (result.success === 0) {
          this.$message.error(`全部失败（${result.failed}）`);
        } else {
          this.$message.warning(`部分成功：${result.success} 成功，${result.failed} 失败`);
        }
      } catch (e) {
        console.error('批量导出失败', e);
        this.$message.error('批量导出失败: ' + (e.message || e));
      } finally {
        this.batchExporting = false;
      }
    },

    onBatchExportDialogClose() {
      // 关闭后清掉结果，下次打开重新加载
      this.batchExportResults = null;
    },
  },
};
