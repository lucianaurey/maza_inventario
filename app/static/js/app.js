/* MAZA · Panel interno de gestión */
(function () {
    "use strict";

    const RED = "#E10600";
    const INK = "#121212";
    const GREY = "#B8BBC2";

    // ---------- menú lateral ----------
    const toggle = document.getElementById("sidebarToggle");
    const backdrop = document.getElementById("sidebarBackdrop");
    if (toggle) toggle.addEventListener("click", () => document.body.classList.toggle("sidebar-open"));
    if (backdrop) backdrop.addEventListener("click", () => document.body.classList.remove("sidebar-open"));

    // ---------- utilidades ----------
    const fmtBs = (n) => "Bs " + Number(n || 0).toLocaleString("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    // ---------- DataTables ----------
    const DT_ES = {
        decimal: ",", thousands: ".", processing: "Procesando...", search: "Buscar:", lengthMenu: "Mostrar _MENU_",
        info: "_START_ a _END_ de _TOTAL_", infoEmpty: "Sin registros", infoFiltered: "(de _MAX_)",
        loadingRecords: "Cargando...", zeroRecords: "No se encontraron resultados", emptyTable: "No hay datos",
        paginate: { first: "Primero", previous: "‹", next: "›", last: "Último" },
    };
    window.MAZA_DT_ES = DT_ES;
    if (window.jQuery && jQuery.fn.dataTable) {
        jQuery("table.js-datatable").each(function () {
            const $t = jQuery(this);
            const order = $t.data("order");
            const titulo = $t.data("export-title") || document.title;
            $t.DataTable({
                language: DT_ES,
                pageLength: Number($t.data("page-length") || 25),
                order: order !== undefined ? order : [],
                dom: "<'row g-2 align-items-center mb-2'<'col-md-6'B><'col-md-6'f>>t<'row g-2 align-items-center mt-2'<'col-md-6'i><'col-md-6'p>>",
                buttons: [
                    { extend: "excelHtml5", text: '<i class="fa-solid fa-file-excel"></i> Excel', title: titulo },
                    { extend: "csvHtml5", text: '<i class="fa-solid fa-file-csv"></i> CSV', title: titulo },
                    { extend: "print", text: '<i class="fa-solid fa-print"></i> Imprimir', title: titulo },
                ],
                columnDefs: [{ targets: "no-sort", orderable: false }],
            });
        });
    }

    // ---------- gráficos ----------
    if (window.Chart) {
        Chart.defaults.font.family = "Inter, system-ui, sans-serif";
        Chart.defaults.color = "#6B6F76";
        Chart.defaults.plugins.legend.labels.boxWidth = 12;
    }
    window.MAZA = {
        RED, INK, GREY, fmtBs, esc,
        palette: [RED, INK, "#7A7D84", "#F05A55", "#3B3D42", GREY, "#FF9B97", "#55585E", "#D4D6DA", "#9A0400", "#C9CBD0", "#2A2A2A", "#E8E9EC", "#FF6F69"],
        chart(id, config) {
            const el = document.getElementById(id);
            if (!el || !window.Chart) return null;
            config.options = Object.assign({ responsive: true, maintainAspectRatio: false }, config.options || {});
            return new Chart(el, config);
        },
    };

    // ---------- buscador de productos ----------
    function productSearch(input, { almacenSelect = null, onSelect }) {
        const box = input.closest(".search-box");
        const results = box.querySelector(".search-results");
        let timer = null;
        let items = [];
        let active = -1;
        const url = input.dataset.url;

        function render() {
            if (!items.length) {
                results.innerHTML = '<div class="search-item"><span class="muted">Sin coincidencias</span></div>';
            } else {
                results.innerHTML = items.map((p, i) => `
                    <div class="search-item ${i === active ? "active" : ""}" data-i="${i}">
                        <div><span class="code">${esc(p.codigo)}</span> · ${esc(p.nombre)}<small>${esc(p.aplicacion)}</small></div>
                        <div class="text-end"><b>${p.stock}</b><small>stock</small></div>
                    </div>`).join("");
            }
            results.classList.add("show");
        }
        function choose(i) {
            const p = items[i];
            if (!p) return;
            results.classList.remove("show");
            input.value = "";
            onSelect(p);
        }
        input.addEventListener("input", () => {
            clearTimeout(timer);
            const q = input.value.trim();
            if (q.length < 2) { results.classList.remove("show"); return; }
            timer = setTimeout(async () => {
                const alm = almacenSelect ? almacenSelect.value : "";
                const r = await fetch(`${url}?q=${encodeURIComponent(q)}&almacen_id=${alm}`);
                items = await r.json();
                active = items.length ? 0 : -1;
                render();
            }, 220);
        });
        input.addEventListener("keydown", (e) => {
            if (!results.classList.contains("show")) return;
            if (e.key === "ArrowDown") { active = Math.min(active + 1, items.length - 1); render(); e.preventDefault(); }
            if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); render(); e.preventDefault(); }
            if (e.key === "Enter") { e.preventDefault(); choose(active); }
            if (e.key === "Escape") results.classList.remove("show");
        });
        results.addEventListener("mousedown", (e) => {
            const item = e.target.closest(".search-item");
            if (item && item.dataset.i !== undefined) choose(Number(item.dataset.i));
        });
        input.addEventListener("blur", () => setTimeout(() => results.classList.remove("show"), 150));
    }
    window.MAZA.productSearch = productSearch;

    // selector de un solo producto (ajuste, transferencia, pedido no atendido)
    document.querySelectorAll("[data-single-product]").forEach((wrap) => {
        const input = wrap.querySelector("input.product-search");
        const hidden = document.getElementById(wrap.dataset.target);
        const view = wrap.querySelector(".selected-product");
        const almacen = wrap.dataset.almacen ? document.getElementById(wrap.dataset.almacen) : null;
        productSearch(input, {
            almacenSelect: almacen,
            onSelect(p) {
                hidden.value = p.id;
                view.innerHTML = `<span class="code">${esc(p.codigo)}</span> · ${esc(p.nombre)}
                    <div class="small-text muted">${esc(p.aplicacion)}</div>
                    <div class="small-text">Stock en el almacén elegido: <b>${p.stock}</b> · total: <b>${p.stock_total}</b></div>`;
                view.classList.remove("d-none");
            },
        });
    });

    // ---------- documento con líneas (venta / compra) ----------
    const doc = document.getElementById("docForm");
    if (doc) {
        const tbody = doc.querySelector("#lines tbody");
        const empty = doc.querySelector("#linesEmpty");
        const almacen = doc.querySelector("#almacen_id");
        const tipoPrecio = doc.querySelector("#tipo_precio");
        const descuento = doc.querySelector("#descuento");
        const totalEl = doc.querySelector("#docTotal");
        const modo = doc.dataset.mode; // venta | compra

        function precioDe(p) {
            if (modo === "compra") return p.costo;
            return tipoPrecio && tipoPrecio.value === "minorista" ? p.precio_sugerido : p.precio_mayorista;
        }
        function recalc() {
            let total = 0;
            tbody.querySelectorAll("tr").forEach((tr) => {
                const c = Number(tr.querySelector(".qty").value || 0);
                const pr = Number(String(tr.querySelector(".price").value || 0).replace(",", "."));
                const sub = c * pr;
                total += sub;
                tr.querySelector(".sub").textContent = fmtBs(sub);
                if (modo === "venta") {
                    const stock = Number(tr.dataset.stock);
                    tr.querySelector(".stock-flag").innerHTML = c > stock
                        ? `<span class="estado agotado">Faltan ${c - stock}</span>`
                        : `<span class="estado ok">OK</span>`;
                }
            });
            if (descuento) total -= Number(String(descuento.value || 0).replace(",", "."));
            totalEl.textContent = fmtBs(Math.max(total, 0));
            empty.classList.toggle("d-none", tbody.children.length > 0);
        }
        function addLine(p, cantidad = 1, precio = null) {
            const existente = tbody.querySelector(`tr[data-id="${p.id}"]`);
            if (existente) {
                const q = existente.querySelector(".qty");
                q.value = Number(q.value) + cantidad;
                recalc();
                return;
            }
            const tr = document.createElement("tr");
            tr.dataset.id = p.id;
            tr.dataset.stock = p.stock;
            tr._p = p;
            tr.innerHTML = `
                <td><input type="hidden" name="producto_id[]" value="${p.id}"><span class="code">${esc(p.codigo)}</span>
                    <div class="small-text muted">${esc(p.nombre)}</div></td>
                <td class="num">${p.stock}</td>
                <td><input class="form-control form-control-sm qty" name="cantidad[]" type="number" min="1" value="${cantidad}"></td>
                <td><input class="form-control form-control-sm price" name="precio[]" type="number" min="0" step="0.01" value="${precio ?? precioDe(p)}"></td>
                <td class="num sub"></td>
                ${modo === "venta" ? '<td class="stock-flag"></td>' : ""}
                <td><button type="button" class="btn btn-sm btn-light-line remove" title="Quitar"><i class="fa-solid fa-xmark"></i></button></td>`;
            tbody.appendChild(tr);
            recalc();
        }
        tbody.addEventListener("input", recalc);
        tbody.addEventListener("click", (e) => {
            if (e.target.closest(".remove")) { e.target.closest("tr").remove(); recalc(); }
        });
        if (descuento) descuento.addEventListener("input", recalc);
        if (tipoPrecio) tipoPrecio.addEventListener("change", () => {
            tbody.querySelectorAll("tr").forEach((tr) => { tr.querySelector(".price").value = precioDe(tr._p); });
            recalc();
        });
        if (almacen && modo === "venta") almacen.addEventListener("change", () => {
            if (tbody.children.length) alert("Cambiaste de almacén: el stock mostrado de las líneas ya agregadas corresponde al almacén anterior. Vuelve a agregarlas si necesitas verificarlo.");
        });
        productSearch(doc.querySelector("input.product-search"), { almacenSelect: almacen, onSelect: (p) => addLine(p) });

        const pre = document.getElementById("precarga");
        if (pre) JSON.parse(pre.textContent).forEach((p) => addLine({ ...p, costo: p.precio }, p.cantidad, p.precio));

        doc.addEventListener("submit", (e) => {
            if (!tbody.children.length) { e.preventDefault(); alert("Agrega al menos un producto."); }
        });
        recalc();
    }
})();
