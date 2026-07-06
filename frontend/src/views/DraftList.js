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
        <el-form :inline="true" :model="filters" size="small">
          <el-form-item label="状态">
            <el-select v-model="filters.status" placeholder="全部" clearable style="width:120px">
              <el-option label="草稿" value="draft" />
              <el-option label="已导出" value="finalized" />
              <el-option label="已归档" value="archived" />
            </el-select>
          </el-form-item>
          <el-form-item label="课程名称">
            <el-input v-model="filters.keyword" placeholder="搜索..." clearable style="width:180px" />
          </el-form-item>
          <el-form-item label="类型">
            <el-select v-model="filters.type" placeholder="全部" clearable style="width:120px">
              <el-option label="个人报告" value="record" />
              <el-option label="批量报告" value="batch" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <div class="btn-group">
              <el-button type="primary" @click="search">查询</el-button>
              <el-button @click="resetFilters">重置</el-button>
            </div>
          </el-form-item>
        </el-form>
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
              size="small" type="danger" :disabled="selectedIds.length === 0"
              @click="confirmBatchDelete"
              :loading="batchDeleting"
            >
              批量删除
            </el-button>
          </div>
          <el-table
            ref="tableRef"
            :data="items" stripe style="width:100%"
            @selection-change="onSelectionChange"
            row-key="rowKey"
          >
            <el-table-column type="selection" width="40" />
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag v-if="row._type === 'batch'" type="success" size="small">批量报告</el-tag>
              <el-tag v-else type="info" size="small" effect="plain">个人报告</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="course_topic" label="课程名称" min-width="160" />
          <el-table-column label="班级" width="120">
            <template #default="{ row }">
              <span v-if="row._type === 'batch'">{{ row.class_name || '-' }}</span>
              <span v-else style="color:#909399;">-</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="最后修改" width="170">
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
  `,

  data() {
    return {
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
      loading: false,
      filters: { status: '', keyword: '', type: '' },
      selectedIds: [],
      selectAll: false,
      isIndeterminate: false,
      batchDeleting: false,
    };
  },

  mounted() {
    this.loadList();
  },

  methods: {
    async loadList() {
      this.loading = true;
      try {
        const params = { page: this.page, page_size: this.pageSize };
        if (this.filters.status) params.status = this.filters.status;
        if (this.filters.keyword) params.keyword = this.filters.keyword;

        // —— 同步加载 CourseRecord 和 BatchReport ——
        const [recordResult, batchResult] = await Promise.all([
          API.reports.list(params),
          API.batchReports.listAll(params),
        ]);

        // 添加类型标记和唯一行键
        const records = (recordResult.items || []).map(r => ({
          ...r,
          _type: 'record',
          rowKey: 'record_' + r.id,
        }));
        const batches = (batchResult.items || []).map(b => ({
          ...b,
          _type: 'batch',
          rowKey: 'batch_' + b.id,
        }));

        // 类型筛选（前端过滤）
        let merged = [...records, ...batches];
        if (this.filters.type === 'record') {
          merged = merged.filter(i => i._type === 'record');
        } else if (this.filters.type === 'batch') {
          merged = merged.filter(i => i._type === 'batch');
        }

        // 按创建时间倒序
        merged.sort((a, b) => {
          const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
          const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
          return tb - ta;
        });

        // 分页本地（两边的分页独立，合并后总数 = 两边之和）
        this.total = merged.length;
        // 服务端已经各自分了页，但合并后总数是两边的 sum
        // 注意：当筛选状态或关键词时，两边各自独立分页，合并结果可能不准
        // 简单处理：作为本地分页合并
        const start = (this.page - 1) * this.pageSize;
        this.items = merged.slice(start, start + this.pageSize);
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
      this.filters = { status: '', keyword: '', type: '' };
      this.page = 1;
      this.loadList();
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
        // 批量报告 → 跳转到批量页面，带上 batch_id
        window.location.hash = '#batch?id=' + row.id;
      } else {
        this.Router.navigate('editor?id=' + row.id);
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
  },
};
