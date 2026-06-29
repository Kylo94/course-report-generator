/**
 * 简易哈希路由
 * 通过 window.location.hash 切换页面视图
 */

const Router = {
  routes: {},
  current: 'dashboard',

  register(name, component) {
    this.routes[name] = component;
  },

  getHash() {
    const hash = window.location.hash.slice(1) || 'dashboard';
    return hash.split('?')[0];
  },

  getParams() {
    const hash = window.location.hash.slice(1);
    const idx = hash.indexOf('?');
    if (idx === -1) return {};
    const params = {};
    new URLSearchParams(hash.slice(idx + 1)).forEach((v, k) => { params[k] = v; });
    return params;
  },

  navigate(name) {
    window.location.hash = '#' + name;
  },

  start(app) {
    const handler = () => {
      const route = this.getHash();
      this.current = route;
      app.currentRoute = route;
      app.currentView = this.routes[route] || this.routes['dashboard'];
      app.pageTitle = this.getTitle(route);
      app.editingRecordId = this.getParams().id || null;
    };
    window.addEventListener('hashchange', handler);
    handler();
  },

  getTitle(route) {
    const titles = {
      dashboard: '首页',
      drafts: '草稿管理',
      'editor?new': '新建报告',
      editor: '报告编辑',
      students: '学生管理',
      classes: '班级管理',
      templates: '模板管理',
      batch: '批量生成',
    };
    return titles[route] || '课程报告生成工具';
  },
};
