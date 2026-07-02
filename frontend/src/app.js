/**
 * 应用入口
 * 初始化 Vue 3 应用，注册路由和组件
 */

const app = Vue.createApp({
  data() {
    return {
      currentRoute: 'dashboard',
      currentView: 'view-dashboard',
      pageTitle: '首页',
      editingRecordId: null,
    };
  },

  methods: {
    navigateTo(index) {
      Router.navigate(index);
    },
  },

  mounted() {
    Router.start(this);
  },
});

// 注册 Element Plus
app.use(ElementPlus);

// 注册图标
for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, component);
}

// 注册视图组件（使动态组件支持字符串引用）
app.component('view-dashboard', DashboardView);
app.component('view-drafts', DraftListView);
app.component('view-editor', ReportEditorView);
app.component('view-students', StudentsView);
app.component('view-classes', ClassesView);
app.component('view-templates', TemplateManagerView);
app.component('view-batch', BatchReportView);
app.component('view-settings', SettingsView);

// 路由注册（使用组件名而非对象）
Router.register('dashboard', 'view-dashboard');
Router.register('drafts', 'view-drafts');
Router.register('editor', 'view-editor');
Router.register('students', 'view-students');
Router.register('classes', 'view-classes');
Router.register('templates', 'view-templates');
Router.register('batch', 'view-batch');
Router.register('settings', 'view-settings');

// 暴露全局对象给所有组件
app.config.globalProperties.Router = Router;
app.config.globalProperties.API = API;

app.mount('#app');
