/**
 * 学生管理页面
 * CRUD 表格 + 批量导入
 */
const StudentsView = {
  template: `
    <div>
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input v-model="searchKeyword" placeholder="搜索学生姓名" style="width:240px" clearable
          @clear="loadStudents" @keyup.enter="loadStudents" />
        <el-button type="primary" @click="loadStudents">搜索</el-button>
        <el-button type="success" @click="showCreateDialog">+ 新建学生</el-button>
        <el-button @click="showImportDialog = true">📥 批量导入</el-button>
      </div>

      <!-- 数据表格 -->
      <el-table :data="students" v-loading="loading" stripe style="width:100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column prop="gender" label="性别" width="60">
          <template #default="{ row }">{{ row.gender || '-' }}</template>
        </el-table-column>
        <el-table-column prop="grade" label="年级" width="80">
          <template #default="{ row }">{{ row.grade || '-' }}</template>
        </el-table-column>
        <el-table-column prop="base_level" label="水平" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="levelType(row.base_level)">{{ row.base_level || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="characteristics" label="特点" min-width="150">
          <template #default="{ row }">
            <el-tag v-for="c in (row.characteristics || [])" :key="c" size="small" style="margin:2px">{{ c }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="parent_contact" label="家长联系方式" width="160">
          <template #default="{ row }">{{ row.parent_contact || '-' }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="120">
          <template #default="{ row }">{{ row.note || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="editStudent(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteStudent(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadStudents"
        />
      </div>

      <!-- 创建/编辑对话框 -->
      <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑学生' : '新建学生'" width="500px">
        <el-form ref="formRef" :model="form" label-width="100px" size="small">
          <el-form-item label="姓名" required>
            <el-input v-model="form.name" maxlength="20" />
          </el-form-item>
          <el-form-item label="性别">
            <el-select v-model="form.gender" placeholder="选择" style="width:120px">
              <el-option label="男" value="男" />
              <el-option label="女" value="女" />
            </el-select>
          </el-form-item>
          <el-form-item label="年级">
            <el-input v-model="form.grade" maxlength="20" />
          </el-form-item>
          <el-form-item label="基础水平">
            <el-select v-model="form.base_level" placeholder="选择" style="width:140px">
              <el-option label="入门" value="入门" />
              <el-option label="初级" value="初级" />
              <el-option label="中级" value="中级" />
              <el-option label="高级" value="高级" />
            </el-select>
          </el-form-item>
          <el-form-item label="学生特点">
            <el-input v-model="characteristicsInput" placeholder="输入特点后回车" style="width:300px"
              maxlength="20" @keyup.enter="addCharacteristic" />
            <div style="margin-top:4px;">
              <el-tag v-for="(c, i) in form.characteristics" :key="i" closable
                @close="form.characteristics.splice(i, 1)" style="margin:2px">
                {{ c }}
              </el-tag>
            </div>
          </el-form-item>
          <el-form-item label="家长联系方式">
            <el-input v-model="form.parent_contact" maxlength="50" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="form.note" type="textarea" :rows="2" maxlength="200" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="saveStudent" :loading="saving">保存</el-button>
        </template>
      </el-dialog>

      <!-- 批量导入弹窗 -->
      <el-dialog v-model="showImportDialog" title="批量导入学生" width="400px">
        <el-upload
          :http-request="handleBatchImport"
          accept=".xlsx,.xls,.csv"
          :show-file-list="false"
        >
          <el-button type="primary">选择 Excel/CSV 文件</el-button>
        </el-upload>
        <div style="margin-top:12px;color:#909399;font-size:13px;">
          支持 .xlsx / .xls / .csv 格式，列名需包含：姓名。
        </div>
        <template #footer>
          <el-button @click="showImportDialog = false">关闭</el-button>
        </template>
      </el-dialog>
    </div>
  `,

  data() {
    return {
      students: [],
      loading: false,
      searchKeyword: '',
      page: 1,
      pageSize: 20,
      total: 0,

      dialogVisible: false,
      isEditing: false,
      editingId: null,
      saving: false,
      characteristicsInput: '',
      form: this.getEmptyForm(),

      showImportDialog: false,
    };
  },

  async mounted() {
    await this.loadStudents();
  },

  methods: {
    getEmptyForm() {
      return {
        name: '',
        gender: '',
        grade: '',
        base_level: '',
        characteristics: [],
        parent_contact: '',
        note: '',
      };
    },

    levelType(level) {
      return { '入门': 'info', '初级': '', '中级': 'warning', '高级': 'success' }[level] || 'info';
    },

    addCharacteristic() {
      const val = this.characteristicsInput.trim();
      if (val && !this.form.characteristics.includes(val)) {
        this.form.characteristics.push(val);
      }
      this.characteristicsInput = '';
    },

    async loadStudents() {
      this.loading = true;
      try {
        const result = await API.students.list({
          keyword: this.searchKeyword || undefined,
          page: this.page,
          page_size: this.pageSize,
        });
        this.students = result.items;
        this.total = result.total;
      } catch (e) {
        this.$message.error('加载学生列表失败: ' + e.message);
      } finally {
        this.loading = false;
      }
    },

    showCreateDialog() {
      this.isEditing = false;
      this.editingId = null;
      this.form = this.getEmptyForm();
      this.characteristicsInput = '';
      this.dialogVisible = true;
    },

    editStudent(row) {
      this.isEditing = true;
      this.editingId = row.id;
      this.form = {
        name: row.name,
        gender: row.gender || '',
        grade: row.grade || '',
        base_level: row.base_level || '',
        characteristics: row.characteristics ? [...row.characteristics] : [],
        parent_contact: row.parent_contact || '',
        note: row.note || '',
      };
      this.characteristicsInput = '';
      this.dialogVisible = true;
    },

    async saveStudent() {
      if (!this.form.name) {
        this.$message.warning('姓名不能为空');
        return;
      }
      this.saving = true;
      try {
        if (this.isEditing) {
          await API.students.update(this.editingId, this.form);
          this.$message.success('学生已更新');
        } else {
          await API.students.create(this.form);
          this.$message.success('学生已创建');
        }
        this.dialogVisible = false;
        await this.loadStudents();
      } catch (e) {
        this.$message.error('操作失败: ' + e.message);
      } finally {
        this.saving = false;
      }
    },

    deleteStudent(row) {
      this.$confirm(`确定删除学生「${row.name}」？`, '确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      }).then(async () => {
        try {
          await API.students.delete(row.id);
          this.$message.success('已删除');
          await this.loadStudents();
        } catch (e) {
          this.$message.error('删除失败: ' + e.message);
        }
      }).catch(() => {});
    },

    async handleBatchImport(options) {
      try {
        await API.importStudents(options.file);
        this.$message.success('批量导入成功');
        this.showImportDialog = false;
        await this.loadStudents();
      } catch (e) {
        this.$message.error('导入失败: ' + e.message);
      }
    },
  },
};
