const localHosts = new Set(["localhost", "127.0.0.1", "[::1]"]);
const apiOrigin = localHosts.has(location.hostname)
  ? "http://localhost:8000"
  : "https://notely-xf7b.onrender.com";

export const API_BASE_URL = `${apiOrigin}/api/v1`;
export const WORKSPACE_URL = "workspace.html";
export const LOGIN_URL = "login.html";
