/**
 * 首页组件
 * 显示概览统计 + 快捷操作 + 最近草稿
 */
const DashboardView = {
  template: `
    <div>
      <h2 style="margin-bottom: 20px;">👋 欢迎使用课程报告生成工具</h2>

      <!-- 统计卡片 -->
      <div class="dashboard-stats">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-icon">
            <el-icon :size="28" color="#409eff"><DocumentCopy /></el-icon>
          </div>
          <div class="stat-number">{{ draftCount }}</div>
          <div class="stat-label">草稿数量</div>
        </el-card>
        <el-card class="stat-card" shadow="hover">
          <div class="stat-icon">
            <el-icon :size="28" color="#67c23a"><User /></el-icon>
          </div>
          <div class="stat-number">{{ studentCount }}</div>
          <div class="stat-label">学生总数</div>
        </el-card>
        <el-card class="stat-card" shadow="hover">
          <div class="stat-icon">
            <el-icon :size="28" color="#e6a23c"><CircleCheckFilled /></el-icon>
          </div>
          <div class="stat-number">{{ finalizedCount }}</div>
          <div class="stat-label">已导出报告</div>
        </el-card>
      </div>

      <!-- 快捷操作 -->
      <el-row :gutter="16" style="margin-bottom: 20px;">
        <el-col :span="8">
          <el-card class="dashboard-card dashboard-card-primary" shadow="hover" @click="startNewReport">
            <el-icon :size="36" color="#fff" style="background:linear-gradient(135deg,#409eff,#667eea);padding:12px;border-radius:12px;"><Plus /></el-icon>
            <h3>新建报告</h3>
            <p>选择学生 → AI 生成 → 编辑 → 导出</p>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card class="dashboard-card" shadow="hover" @click="Router.navigate('drafts')">
            <el-icon :size="36" color="#67c23a" style="background:rgba(103,194,58,0.1);padding:12px;border-radius:12px;"><Document /></el-icon>
            <h3>草稿管理</h3>
            <p>查看、编辑、删除已保存的草稿</p>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card class="dashboard-card" shadow="hover" @click="Router.navigate('editor?new')">
            <el-icon :size="36" color="#e6a23c" style="background:rgba(230,162,60,0.1);padding:12px;border-radius:12px;"><Edit /></el-icon>
            <h3>快速编辑</h3>
            <p>直接进入报告编辑器</p>
          </el-card>
        </el-col>
      </el-row>

      <!-- 最近草稿 -->
      <el-card>
        <template #header>
          <span>📄 最近草稿</span>
        </template>
        <div v-if="recentDrafts.length === 0" class="empty-state">
          <p>暂无草稿，点击上方"新建报告"开始</p>
        </div>
        <el-table v-else :data="recentDrafts" stripe style="width: 100%">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="course_topic" label="课程名称" min-width="150" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="180">
            <template #default="{ row }">
              {{ formatDate(row.updated_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="openDraft(row.id)">
                打开
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  `,

  data() {
    return {
      draftCount: 0,
      studentCount: 0,
      finalizedCount: 0,
      recentDrafts: [],
    };
  },

  async mounted() {
    await this.loadStats();
    await this.loadRecentDrafts();
  },

  methods: {
    async loadStats() {
      try {
        const [drafts, students] = await Promise.all([
          API.reports.list({ page_size: 1 }),
          API.students.list({ page_size: 1 }),
        ]);
        this.draftCount = drafts.total;
        this.studentCount = students.total;

        // 已导出报告数量
        const finalized = await API.reports.list({ status: 'finalized', page_size: 1 });
        this.finalizedCount = finalized.total;
      } catch (e) {
        console.error('加载统计失败:', e);
      }
    },

    async loadRecentDrafts() {
      try {
        const result = await API.reports.list({ page_size: 5 });
        this.recentDrafts = result.items;
      } catch (e) {
        console.error('加载草稿列表失败:', e);
      }
    },

    startNewReport() {
      this.Router.navigate('editor?new');
    },

    openDraft(id) {
      this.Router.navigate('editor?id=' + id);
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
