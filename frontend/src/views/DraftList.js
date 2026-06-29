/**
 * 草稿管理列表页面
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
          <el-form-item>
            <el-button type="primary" @click="search">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
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
        <el-table v-else :data="items" stripe style="width:100%">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="course_topic" label="课程名称" min-width="160" />
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
                <el-button size="small" type="primary" link @click="openDraft(row.id)">
                  编辑
                </el-button>
                <el-button
                  v-if="row.status === 'draft'"
                  size="small" type="success" link @click="finalizeDraft(row.id)"
                >
                  标记已导出
                </el-button>
                <el-button size="small" type="danger" link @click="confirmDelete(row.id)">
                  删除
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

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
      filters: { status: '', keyword: '' },
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
        const result = await API.reports.list(params);
        this.items = result.items;
        this.total = result.total;
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
      this.filters = { status: '', keyword: '' };
      this.page = 1;
      this.loadList();
    },

    openDraft(id) {
      this.Router.navigate('editor?id=' + id);
    },

    async finalizeDraft(id) {
      try {
        await API.reports.updateStatus(id, 'finalized');
        this.$message.success('已标记为已导出');
        this.loadList();
      } catch (e) {
        this.$message.error('操作失败: ' + e.message);
      }
    },

    confirmDelete(id) {
      this.$confirm('确定删除此记录？此操作不可撤销。', '确认删除', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      }).then(async () => {
        try {
          await API.reports.delete(id);
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
