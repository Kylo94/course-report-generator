/**
 * API 客户端
 * 封装 HTTP 请求，统一错误处理
 */

const API = {
  baseURL: '',

  async request(method, url, data = null) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (data && method !== 'GET') {
      opts.body = JSON.stringify(data);
    }
    try {
      const resp = await fetch(this.baseURL + url, opts);
      if (resp.status === 204) return null;
      const json = await resp.json();
      if (!resp.ok) {
        const detail = json.detail || `HTTP ${resp.status}`;
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
      }
      return json;
    } catch (err) {
      if (err.message.includes('Failed to fetch')) {
        throw new Error('无法连接后端服务，请确认服务已启动');
      }
      throw err;
    }
  },

  get(url) { return this.request('GET', url); },
  post(url, data) { return this.request('POST', url, data); },
  put(url, data) { return this.request('PUT', url, data); },
  patch(url, data) { return this.request('PATCH', url, data); },
  delete(url) { return this.request('DELETE', url); },

  // 文件上传
  async upload(url, file) {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch(this.baseURL + url, { method: 'POST', body: formData });
    if (!resp.ok) {
      const json = await resp.json();
      throw new Error(json.detail || '上传失败');
    }
    return resp.json();
  },

  // =====================
  // 报告 API
  // =====================
  reports: {
    create(data) { return API.post('/api/reports', data); },
    list(params = {}) {
      const q = new URLSearchParams();
      if (params.student_id) q.set('student_id', params.student_id);
      if (params.status) q.set('status', params.status);
      if (params.keyword) q.set('keyword', params.keyword);
      if (params.page) q.set('page', params.page);
      if (params.page_size) q.set('page_size', params.page_size);
      const qs = q.toString();
      return API.get(`/api/reports${qs ? '?' + qs : ''}`);
    },
    get(id) { return API.get(`/api/reports/${id}`); },
    update(id, data) { return API.put(`/api/reports/${id}`, data); },
    patch(id, data) { return API.patch(`/api/reports/${id}`, data); },
    delete(id) { return API.delete(`/api/reports/${id}`); },
    updateStatus(id, status) { return API.patch(`/api/reports/${id}/status`, { status }); },
    export(id, templateId = 'classic') { return API.post(`/api/reports/${id}/export`, { template_id: templateId }); },
  },

  // =====================
  // 学生 API
  // =====================
  students: {
    list(params = {}) {
      const q = new URLSearchParams();
      if (params.keyword) q.set('keyword', params.keyword);
      if (params.page) q.set('page', params.page);
      if (params.page_size) q.set('page_size', params.page_size);
      const qs = q.toString();
      return API.get(`/api/students${qs ? '?' + qs : ''}`);
    },
    get(id) { return API.get(`/api/students/${id}`); },
    create(data) { return API.post('/api/students', data); },
  },

  // =====================
  // AI API
  // =====================
  ai: {
    generate(data) { return API.post('/api/ai/generate', data); },
    regenerate(data) { return API.post('/api/ai/regenerate', data); },
    providers() { return API.get('/api/ai/providers'); },
  },

  // =====================
  // 资产管理
  // =====================
  assets: {
    uploadScreenshot(file) { return API.upload('/api/assets/screenshot', file); },
    uploadLogo(file) { return API.upload('/api/assets/logo', file); },
    getLogo() { return API.get('/api/assets/logo'); },
  },

  // =====================
  // 模板管理
  // =====================
  templates: {
    list() { return API.get('/api/templates'); },
  },
};
