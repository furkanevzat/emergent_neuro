// Neurocircuit API Client
const API_BASE = window.location.hostname === 'localhost' 
  ? 'http://localhost:8001'
  : 'https://pcb-pool.preview.emergentagent.com';

// Auth helpers
function getToken() {
  return localStorage.getItem('access_token');
}

function getUser() {
  const userStr = localStorage.getItem('user');
  return userStr ? JSON.parse(userStr) : null;
}

function isAuthenticated() {
  return !!getToken();
}

function logout() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('user');
  window.location.href = '/home.html';
}

// API client with auth
async function apiCall(endpoint, options = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers
  });
  
  if (response.status === 401) {
    // Unauthorized - redirect to auth
    logout();
    return null;
  }
  
  return response;
}

// Protected page check
function requireAuth() {
  if (!isAuthenticated()) {
    window.location.href = '/authorization.html';
    return false;
  }
  return true;
}

// Format date
function formatDate(dateStr) {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// Status badge helper
function getStatusBadge(status) {
  const badges = {
    reviewing: '<span class="badge badge-yellow">Reviewing</span>',
    quoted: '<span class="badge badge-blue">Quoted</span>',
    production: '<span class="badge badge-blue">Production</span>',
    shipped: '<span class="badge badge-green">Shipped</span>',
    delivered: '<span class="badge badge-green">Delivered</span>'
  };
  return badges[status] || '<span class="badge badge-gray">Unknown</span>';
}
