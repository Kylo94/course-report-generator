/**
 * 应用入口
 * 初始化 Vue 3 应用，注册路由和组件
 */

// 注册路由
Router.register('dashboard', DashboardView);
Router.register('drafts', DraftListView);
Router.register('editor', ReportEditorView);
Router.register('students', StudentsView);
Router.register('classes', ClassesView);

// 创建 Vue 应用
const App = {
  data() {
    return {
      currentRoute: 'dashboard',
      currentView: null,
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
    // 将 Router 实例暴露给子组件
    DashboardView.data().Router = Router;
    DraftListView.data().Router = Router;
    ReportEditorView.data().Router = Router;
    StudentsView.data().Router = Router;
    ClassesView.data().Router = Router;

    // 启动路由
    Router.start(this);
  },
};

const app = Vue.createApp(App);

// 注册 Element Plus
app.use(ElementPlus);

// 注册图标
for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, component);
}

app.mount('#app');
