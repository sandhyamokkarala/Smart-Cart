const API = "";
const state = {
  token: localStorage.getItem("smartcart-token") || "",
  customer: JSON.parse(localStorage.getItem("smartcart-customer") || "null"),
  cart: [],
  products: [],
  authMode: "login",
};

const el = (id) => document.getElementById(id);
const money = (value) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value || 0));
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(`${API}${path}`, { ...options, headers });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail || "Something went wrong. Please try again.");
  return data;
}

let toastTimer;
function toast(message) {
  const node = el("toast");
  node.textContent = message;
  node.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("visible"), 2600);
}

function imageFallback(image, category) {
  const fallback = {
    Electronics: "photo-1505740420928-5e560c06d30e", Home: "photo-1555041469-a586c61ea9bc",
    Fashion: "photo-1523275335684-37898b6baf30", Beauty: "photo-1596462502278-27bfdc403348",
    Sports: "photo-1461896836934-ffe607ba8211",
  }[category] || "photo-1490481651871-ab68de25d43d";
  image.src = `https://images.unsplash.com/${fallback}?auto=format&fit=crop&w=900&q=80`;
  image.onerror = null;
}

async function loadProducts() {
  const params = new URLSearchParams();
  const search = el("searchInput").value.trim();
  const category = el("categoryFilter").value;
  if (search) params.set("search", search);
  if (category) params.set("category", category);
  try {
    state.products = await request(`/products?${params}`);
    renderProducts();
  } catch (error) {
    el("resultCount").textContent = error.message;
  }
}

function renderProducts() {
  const grid = el("productGrid");
  grid.innerHTML = state.products.map((product, index) => `
    <article class="product-card" style="animation-delay:${Math.min(index * 35, 280)}ms">
      <div class="product-photo">
        <img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.product_name)}" loading="lazy" onerror="imageFallback(this,'${escapeHtml(product.category)}')">
        ${product.discount ? `<span class="product-tag">${escapeHtml(product.discount)}% off</span>` : ""}
        <button class="product-quick" data-view="${product.product_id}">Quick look  ↗</button>
      </div>
      <div class="product-info"><div><h3>${escapeHtml(product.product_name)}</h3><p>${escapeHtml(product.category)} <span class="product-rating">· ★ ${Number(product.rating).toFixed(1)}</span></p></div><span class="product-price">${money(product.price * (1 - product.discount / 100))}</span></div>
    </article>`).join("");
  el("resultCount").textContent = `${state.products.length} thoughtful finds`;
  el("emptyState").hidden = state.products.length > 0;
  grid.hidden = state.products.length === 0;
  grid.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => openProduct(Number(button.dataset.view))));
}

function panelOpen(panel) {
  el("scrim").classList.add("visible");
  el(panel).classList.add("open");
  el(panel).setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function panelsClose() {
  document.querySelectorAll(".side-panel").forEach((panel) => {
    panel.classList.remove("open");
    panel.setAttribute("aria-hidden", "true");
  });
  el("scrim").classList.remove("visible");
  document.body.style.overflow = "";
}

async function loadCart() {
  if (!state.customer || !state.token) {
    state.cart = [];
    renderCart();
    return;
  }
  try {
    state.cart = await request(`/cart/${state.customer.customer_id}`);
  } catch { state.cart = []; }
  renderCart();
}

function renderCart() {
  el("cartCount").textContent = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  const container = el("cartItems");
  if (!state.cart.length) {
    container.innerHTML = `<p class="cart-empty">Your bag is taking a quiet moment. Find something you love.</p>`;
  } else {
    container.innerHTML = state.cart.map((item) => `
      <article class="cart-row"><img src="${escapeHtml(item.product.image_url)}" alt="" onerror="imageFallback(this,'${escapeHtml(item.product.category)}')">
        <div><h3>${escapeHtml(item.product.product_name)}</h3><p>${item.quantity} × ${money(item.product.price)}</p><button class="cart-remove" data-remove="${item.cart_id}">Remove</button></div>
        <strong>${money(item.product.price * item.quantity)}</strong></article>`).join("");
    container.querySelectorAll("[data-remove]").forEach((button) => button.addEventListener("click", () => removeCartItem(Number(button.dataset.remove))));
  }
  const subtotal = state.cart.reduce((sum, item) => sum + item.product.price * item.quantity, 0);
  el("cartTotal").textContent = money(subtotal);
  el("checkoutButton").disabled = !state.cart.length;
}

async function addToCart(productId) {
  if (!state.customer) {
    toast("Sign in to add a find to your bag.");
    openAccount();
    return;
  }
  try {
    await request("/cart", { method: "POST", body: JSON.stringify({ customer_id: state.customer.customer_id, product_id: productId, quantity: 1 }) });
    await loadCart();
    toast("Added to your bag.");
  } catch (error) { toast(error.message); }
}

async function removeCartItem(cartId) {
  try {
    await request(`/cart/${cartId}`, { method: "DELETE" });
    await loadCart();
  } catch (error) { toast(error.message); }
}

async function checkout() {
  if (!state.cart.length) return;
  el("checkoutButton").disabled = true;
  try {
    const order = await request("/orders", {
      method: "POST",
      body: JSON.stringify({ payment_method: el("paymentMethod").value, items: state.cart.map((item) => ({ product_id: item.product_id, quantity: item.quantity })) }),
    });
    state.cart = [];
    renderCart();
    await loadProducts();
    panelsClose();
    toast(`Order #${order.order_id} placed. Lovely choice.`);
    await openAccount();
  } catch (error) { toast(error.message); }
  finally { el("checkoutButton").disabled = false; }
}

function setUser(data) {
  state.token = data.access_token;
  state.customer = data.customer;
  localStorage.setItem("smartcart-token", state.token);
  localStorage.setItem("smartcart-customer", JSON.stringify(state.customer));
  el("accountTrigger").textContent = state.customer.name.split(" ")[0];
  el("personalMessage").textContent = "A fresh edit, shaped around what you already love.";
  el("personalAction").textContent = "See your account ↗";
}

function clearUser() {
  state.token = "";
  state.customer = null;
  localStorage.removeItem("smartcart-token");
  localStorage.removeItem("smartcart-customer");
  state.cart = [];
  renderCart();
  el("accountTrigger").textContent = "Sign in";
  el("personalMessage").textContent = "Sign in to see a short list shaped around what you love.";
  el("personalAction").textContent = "Make it personal ↗";
  el("recommendationGrid").innerHTML = "";
}

function authForm() {
  const registering = state.authMode === "register";
  el("accountContent").innerHTML = `
    <form class="account-form" id="authForm">
      ${registering ? `<label>Your name<input name="name" autocomplete="name" required minlength="2" placeholder="Alex Morgan"></label>` : ""}
      <label>Email address<input name="email" type="email" autocomplete="email" required placeholder="you@example.com"></label>
      <label>Password<input name="password" type="password" autocomplete="${registering ? "new-password" : "current-password"}" minlength="8" required placeholder="At least 8 characters"></label>
      ${registering ? `<label>Age<input name="age" type="number" min="13" max="100" value="28" required></label><label>City<input name="city" required minlength="2" placeholder="Portland"></label>` : ""}
      <button class="button button-dark" type="submit">${registering ? "Create your account" : "Sign in"} <span aria-hidden="true">↗</span></button>
    </form>
    <button class="account-switch" id="authSwitch">${registering ? "Already have an account? Sign in" : "New around here? Create an account"}</button>
    <p class="fine-print">Demo customer: customer1@example.com · customer1234</p>`;
  el("authForm").addEventListener("submit", submitAuth);
  el("authSwitch").addEventListener("click", () => { state.authMode = registering ? "login" : "register"; authForm(); });
}

async function submitAuth(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  const path = state.authMode === "register" ? "/register" : "/login";
  if (state.authMode === "register") {
    payload.age = Number(payload.age);
    payload.gender = "Prefer not to say";
  }
  const button = event.currentTarget.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    setUser(await request(path, { method: "POST", body: JSON.stringify(payload) }));
    await loadCart();
    await renderDashboard();
    toast(`Welcome, ${state.customer.name.split(" ")[0]}.`);
  } catch (error) { toast(error.message); button.disabled = false; }
}

async function renderDashboard() {
  if (!state.customer) return authForm();
  el("accountContent").innerHTML = `<p class="cart-empty">Gathering your account…</p>`;
  try {
    const dashboard = await request(`/customer-dashboard/${state.customer.customer_id}`);
    el("accountContent").innerHTML = `
      <div class="dashboard-welcome"><p>GOOD TO SEE YOU, ${escapeHtml(state.customer.name.split(" ")[0].toUpperCase())}</p><h3>Your little corner.</h3></div>
      <div class="account-stats"><div class="account-stat"><span>Orders</span><strong>${dashboard.total_orders}</strong></div><div class="account-stat"><span>Spent</span><strong>${money(dashboard.total_spending)}</strong></div><div class="account-stat"><span>Average order</span><strong>${money(dashboard.average_order_value)}</strong></div><div class="account-stat"><span>Your segment</span><strong>${escapeHtml(dashboard.segment.replace(" Customer", ""))}</strong></div></div>
      <h3 class="account-subhead">Made for you</h3>
      ${dashboard.recommended_products.map((item) => `<div class="dashboard-pick"><span>${escapeHtml(item.product_name)}</span><span>${money(item.price)} · ${Math.round(item.score * 100)}%</span></div>`).join("") || `<p class="cart-empty">More good picks will show up as you shop.</p>`}
      <h3 class="account-subhead">A good hunch</h3>
      ${dashboard.purchase_predictions.map((item) => `<div class="dashboard-pick"><span>${escapeHtml(item.product_name)}</span><span>${Math.round(item.purchase_probability * 100)}% match</span></div>`).join("") || `<p class="cart-empty">No predictions just yet.</p>`}
      <button class="logout-button" id="logoutButton">Sign out</button>`;
    el("logoutButton").addEventListener("click", () => { clearUser(); panelsClose(); toast("You are signed out."); });
    renderRecommendations(dashboard.recommended_products);
  } catch (error) {
    el("accountContent").innerHTML = `<p class="cart-empty">${escapeHtml(error.message)}</p><button class="logout-button" id="logoutButton">Sign out</button>`;
    el("logoutButton").addEventListener("click", clearUser);
  }
}

function renderRecommendations(items) {
  const grid = el("recommendationGrid");
  grid.innerHTML = items.slice(0, 2).map((item) => `
    <article class="recommendation-card"><img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.product_name)}" loading="lazy" onerror="imageFallback(this,'${escapeHtml(item.category)}')"><div><p>${escapeHtml(item.product_name)}</p><span>${money(item.price)} · ${Math.round(item.score * 100)}% match</span></div></article>`).join("");
}

async function openAccount() {
  panelOpen("accountPanel");
  await renderDashboard();
}

async function openCart() {
  await loadCart();
  panelOpen("cartPanel");
}

async function openProduct(productId) {
  panelOpen("productPanel");
  el("productDetail").innerHTML = `<p class="cart-empty">Finding the details…</p>`;
  try {
    const product = await request(`/products/${productId}`);
    let prediction = "";
    if (state.customer) {
      try {
        const result = await request("/predict-purchase", {
          method: "POST",
          body: JSON.stringify({ customer_id: state.customer.customer_id, product_id: product.product_id }),
        });
        prediction = `<p class="detail-prediction">${Math.round(result.purchase_probability * 100)}% chance this is your kind of find.</p>`;
      } catch { prediction = ""; }
    }
    el("productDetail").innerHTML = `
      <img class="detail-image" src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.product_name)}" onerror="imageFallback(this,'${escapeHtml(product.category)}')">
      <div class="detail-meta"><span>${escapeHtml(product.category)}</span><span>★ ${Number(product.rating).toFixed(1)} / 5</span></div>
      <h3 class="detail-name">${escapeHtml(product.product_name)}</h3>
      <div class="detail-price">${money(product.price * (1 - product.discount / 100))}${product.discount ? ` <span class="product-rating">${product.discount}% off</span>` : ""}</div>
      <p class="detail-description">A thoughtful everyday pick, selected for useful details and made to fit right into your routine.</p>
      ${prediction}<p class="detail-stock">${product.stock > 0 ? `${product.stock} ready to ship` : "Currently out of stock"}</p>
      <button class="button button-dark" id="detailAdd" ${product.stock < 1 ? "disabled" : ""}>Add to bag <span aria-hidden="true">↗</span></button>`;
    el("detailAdd").addEventListener("click", async () => {
      await addToCart(product.product_id);
      if (state.customer) panelsClose();
    });
  } catch (error) {
    el("productDetail").innerHTML = `<p class="cart-empty">${escapeHtml(error.message)}</p>`;
  }
}

function chooseCategory(category) {
  el("categoryFilter").value = category;
  document.querySelectorAll(".category-chip").forEach((chip) => chip.classList.toggle("selected", chip.dataset.filter === category));
  loadProducts();
  el("shop").scrollIntoView({ behavior: "smooth" });
}

el("searchInput").addEventListener("input", (() => {
  let timer;
  return () => { clearTimeout(timer); timer = setTimeout(loadProducts, 180); };
})());
el("categoryFilter").addEventListener("change", () => chooseCategory(el("categoryFilter").value));
document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => chooseCategory(button.dataset.filter)));
document.querySelectorAll("[data-category]").forEach((link) => link.addEventListener("click", () => chooseCategory(link.dataset.category)));
el("cartTrigger").addEventListener("click", openCart);
el("accountTrigger").addEventListener("click", openAccount);
el("personalAction").addEventListener("click", openAccount);
el("checkoutButton").addEventListener("click", checkout);
el("scrim").addEventListener("click", panelsClose);
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", panelsClose));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") panelsClose();
  if (event.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
    event.preventDefault();
    el("searchInput").focus();
  }
});

if (state.customer) {
  el("accountTrigger").textContent = state.customer.name.split(" ")[0];
  el("personalMessage").textContent = "A fresh edit, shaped around what you already love.";
  el("personalAction").textContent = "See your account ↗";
  loadCart();
}
loadProducts();