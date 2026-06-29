/**
 * 班级管理页面
 * CRUD 表格
 */
const ClassesView = {
  template: `
    <div>
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-button type="success" @click="showCreateDialog">+ 新建班级</el-button>
      </div>

      <!-- 数据表格 -->
      <el-table :data="classes" v-loading="loading" stripe style="width:100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="班级名称" min-width="150" />
        <el-table-column prop="schedule_day" label="上课日" width="120">
          <template #default="{ row }">{{ row.schedule_day || '-' }}</template>
        </el-table-column>
        <el-table-column prop="schedule_time" label="上课时间" width="120">
          <template #default="{ row }">{{ row.schedule_time || '-' }}</template>
        </el-table-column>
        <el-table-column prop="student_count" label="学生数" width="80" />
        <el-table-column label="排序" width="90">
          <template #default="{ row, $index }">
            <el-button size="small" :disabled="$index === 0" @click="moveUp(row, $index)">▲</el-button>
            <el-button size="small" :disabled="$index === classes.length - 1" @click="moveDown(row, $index)">▼</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewStudents(row)">学生</el-button>
            <el-button size="small" @click="editClass(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteClass(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 创建/编辑对话框 -->
      <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑班级' : '新建班级'" width="400px">
        <el-form :model="form" label-width="100px" size="small">
          <el-form-item label="班级名称" required>
            <el-input v-model="form.name" maxlength="30" />
          </el-form-item>
          <el-form-item label="上课日">
            <el-select v-model="form.schedule_day" placeholder="选择" style="width:140px">
              <el-option label="周一" value="周一" />
              <el-option label="周二" value="周二" />
              <el-option label="周三" value="周三" />
              <el-option label="周四" value="周四" />
              <el-option label="周五" value="周五" />
              <el-option label="周六" value="周六" />
              <el-option label="周日" value="周日" />
            </el-select>
          </el-form-item>
          <el-form-item label="上课时间">
            <el-time-picker v-model="scheduleTime" placeholder="选择时间" format="HH:mm" style="width:140px"
              @change="v => form.schedule_time = v ? v.toTimeString().slice(0,5) : ''" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="saveClass" :loading="saving">保存</el-button>
        </template>
      </el-dialog>
    </div>
  `,

  data() {
    return {
      classes: [],
      loading: false,

      dialogVisible: false,
      isEditing: false,
      editingId: null,
      saving: false,
      form: { name: '', schedule_day: '', schedule_time: '' },
      scheduleTime: null,
    };
  },

  async mounted() {
    await this.loadClasses();
  },

  methods: {
    async loadClasses() {
      this.loading = true;
      try {
        const result = await API.classes.list();
        this.classes = result.items || [];
      } catch (e) {
        this.$message.error('加载班级列表失败: ' + e.message);
      } finally {
        this.loading = false;
      }
    },

    showCreateDialog() {
      this.isEditing = false;
      this.editingId = null;
      this.form = { name: '', schedule_day: '', schedule_time: '' };
      this.scheduleTime = null;
      this.dialogVisible = true;
    },

    viewStudents(row) {
      Router.navigate('students');
    },

    editClass(row) {
      this.isEditing = true;
      this.editingId = row.id;
      this.form = {
        name: row.name,
        schedule_day: row.schedule_day || '',
        schedule_time: row.schedule_time || '',
      };
      if (row.schedule_time) {
        const [h, m] = row.schedule_time.split(':');
        const d = new Date();
        d.setHours(parseInt(h), parseInt(m), 0, 0);
        this.scheduleTime = d;
      }
      this.dialogVisible = true;
    },

    async saveClass() {
      if (!this.form.name) {
        this.$message.warning('班级名称不能为空');
        return;
      }
      this.saving = true;
      try {
        if (this.isEditing) {
          await API.classes.update(this.editingId, this.form);
          this.$message.success('班级已更新');
        } else {
          await API.classes.create(this.form);
          this.$message.success('班级已创建');
        }
        this.dialogVisible = false;
        await this.loadClasses();
      } catch (e) {
        this.$message.error('操作失败: ' + e.message);
      } finally {
        this.saving = false;
      }
    },

    async moveUp(row, index) {
      if (index === 0) return;
      const items = [...this.classes];
      // 交换数组中的位置
      [items[index - 1], items[index]] = [items[index], items[index - 1]];
      // 全部重新索引，确保顺序唯一
      const orders = items.map((item, i) => ({ id: item.id, sort_order: i }));
      try {
        await API.classes.reorder(orders);
        await this.loadClasses();
      } catch (e) {
        this.$message.error('上移失败: ' + e.message);
      }
    },

    async moveDown(row, index) {
      if (index === this.classes.length - 1) return;
      const items = [...this.classes];
      // 交换数组中的位置
      [items[index], items[index + 1]] = [items[index + 1], items[index]];
      // 全部重新索引，确保顺序唯一
      const orders = items.map((item, i) => ({ id: item.id, sort_order: i }));
      try {
        await API.classes.reorder(orders);
        await this.loadClasses();
      } catch (e) {
        this.$message.error('下移失败: ' + e.message);
      }
    },

    deleteClass(row) {
      this.$confirm(`确定删除班级「${row.name}」？`, '确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      }).then(async () => {
        try {
          await API.classes.delete(row.id);
          this.$message.success('已删除');
          await this.loadClasses();
        } catch (e) {
          this.$message.error('删除失败: ' + e.message);
        }
      }).catch(() => {});
    },
  },
};
