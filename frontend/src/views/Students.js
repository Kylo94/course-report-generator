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
        <el-button @click="exportCsv">📤 导出 CSV</el-button>
        <el-button @click="showImportDialog = true">📥 批量导入</el-button>
      </div>

      <!-- 数据表格 -->
      <div v-if="students.length > 0" style="margin-bottom:12px;display:flex;align-items:center;gap:12px;">
        <el-checkbox v-model="selectAll" :indeterminate="isIndeterminate" @change="onSelectAllChange">
          全选
        </el-checkbox>
        <span style="color:#909399;font-size:13px;">已选 {{ selectedIds.length }} 项</span>
        <el-button
          size="small" type="danger" :disabled="selectedIds.length === 0"
          @click="confirmBatchDelete" :loading="batchDeleting"
        >
          批量删除
        </el-button>
      </div>
      <el-table ref="tableRef" :data="students" v-loading="loading" stripe style="width:100%"
        @selection-change="onSelectionChange">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column label="班级" width="120">
          <template #default="{ row }">{{ className(row.class_id) }}</template>
        </el-table-column>
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
          <el-form-item label="所属班级">
            <el-select v-model="form.class_id" placeholder="不分配" clearable style="width:200px">
              <el-option v-for="c in classList" :key="c.id" :label="c.name" :value="c.id" />
            </el-select>
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
      <el-dialog v-model="showImportDialog" title="批量导入学生" width="500px">
        <el-card style="margin-bottom:16px;">
          <template #header>📋 默认值（CSV 中缺失的字段将使用此值）</template>
          <el-form size="small" label-width="90px">
            <el-form-item label="所属班级">
              <el-select v-model="importDefaults.class_id" placeholder="不分配" style="width:200px" clearable>
                <el-option v-for="c in classList" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="基础水平">
              <el-select v-model="importDefaults.base_level" placeholder="入门" style="width:140px">
                <el-option label="入门" value="入门" />
                <el-option label="初级" value="初级" />
                <el-option label="中级" value="中级" />
              </el-select>
            </el-form-item>
            <el-form-item label="年级">
              <el-input v-model="importDefaults.grade" placeholder="留空使用 CSV 中的值" style="width:200px" />
            </el-form-item>
          </el-form>
        </el-card>
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
      classList: [],
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

      // 批量删除
      selectedIds: [],
      selectAll: false,
      isIndeterminate: false,
      batchDeleting: false,

      // 导入默认值
      importDefaults: { class_id: null, base_level: '入门', grade: '' },
    };
  },

  async mounted() {
    await Promise.all([this.loadStudents(), this.loadClasses()]);
  },

  methods: {
    getEmptyForm() {
      return {
        name: '',
        class_id: null,
        gender: '',
        grade: '',
        base_level: '入门',
        characteristics: [],
        parent_contact: '',
        note: '',
      };
    },

    className(classId) {
      if (!classId) return '-';
      const c = this.classList.find(cls => cls.id === classId);
      return c ? c.name : '未知班级';
    },

    async loadClasses() {
      try {
        const result = await API.classes.list();
        this.classList = result.items || [];
      } catch (e) {
        console.error('加载班级列表失败:', e);
      }
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
        class_id: row.class_id || null,
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

    onSelectionChange(selection) {
      this.selectedIds = selection.map(r => r.id);
      this.selectAll = selection.length === this.students.length && this.students.length > 0;
      this.isIndeterminate = selection.length > 0 && selection.length < this.students.length;
    },

    onSelectAllChange(val) {
      if (this.$refs.tableRef) {
        this.$refs.tableRef.clearSelection();
        if (val) {
          this.$nextTick(() => {
            this.students.forEach(r => this.$refs.tableRef.toggleRowSelection(r, true));
          });
        }
      }
    },

    confirmBatchDelete() {
      const count = this.selectedIds.length;
      this.$confirm(`确定删除选中的 ${count} 名学生？此操作不可撤销。`, '批量删除', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      }).then(async () => {
        this.batchDeleting = true;
        try {
          const result = await API.students.batchDelete(this.selectedIds);
          this.$message.success(`成功删除 ${result.deleted} 名学生`);
          this.selectedIds = [];
          this.selectAll = false;
          this.isIndeterminate = false;
          await this.loadStudents();
        } catch (e) {
          this.$message.error('批量删除失败: ' + e.message);
        } finally {
          this.batchDeleting = false;
        }
      }).catch(() => {});
    },

    async handleBatchImport(options) {
      try {
        // 手动构造 FormData，附带默认值
        const formData = new FormData();
        formData.append('file', options.file);
        if (this.importDefaults.class_id) {
          formData.append('default_class_id', String(this.importDefaults.class_id));
        }
        if (this.importDefaults.base_level) {
          formData.append('default_base_level', this.importDefaults.base_level);
        }
        if (this.importDefaults.grade) {
          formData.append('default_grade', this.importDefaults.grade);
        }
        const resp = await fetch(API.baseURL + '/api/import/students', {
          method: 'POST',
          body: formData,
        });
        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.detail || `HTTP ${resp.status}`);
        }
        const result = await resp.json();
        this.$message.success(`导入成功：${result.success} 条（失败 ${result.failed} 条）`);
        this.showImportDialog = false;
        await this.loadStudents();
      } catch (e) {
        this.$message.error('导入失败: ' + e.message);
      }
    },

    exportCsv() {
      const url = API.students.exportCsv({ keyword: this.searchKeyword || undefined });
      window.open(url, '_blank');
    },
  },
};
