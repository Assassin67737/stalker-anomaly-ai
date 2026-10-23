// rays.c — лучемёт по level.cform без движка (20.10.2026).
//
// Тот же статический луч, что у игры: ray_pick с rqtStatic → CObjectSpace::_RayPick →
// CDB OPT_ONLYNEAREST | OPT_CULL. Тест треугольника скопирован из xrCDB/xrCDB_ray.cpp
// (_tri, ветка bCull): задние грани не ловятся, EPS = 1e-5, r <= 0 и r > range отброшены.
// Поэтому попадание сверяется с игрой до номера треугольника (ray_pick:get_element()).
//
// Формат level.cform (xrEngine/xrLevel.h, xrCDB/xrCDB.h):
//   hdrCFORM 36 байт: version u32 (=4), vertcount u32, facecount u32, aabb 6×f32
//   вершины vertcount × (x,y,z f32)
//   треугольники facecount × 16 байт: verts[3] u32, dummy u32 (material:14, флаги:2, sector:16)
//
// Режимы:
//   rays pano  <cform> <points.f32> <out.u16> <ndirs> <range>
//       points = N × (x,y,z) — уже на высоте глаз. Для каждой точки ndirs горизонтальных
//       лучей (азимут a_i = 2π·i/ndirs, dir = (cos a, 0, sin a)). Ответ — дистанция в см
//       (u16), 65535 = до range ничего нет.
//   rays probe <cform> <rays.f32> <out.bin>
//       rays = N × (ox,oy,oz, dx,dy,dz, range). Ответ: N × (dist f32, tri i32), tri = -1 мимо.
//   rays seg   <cform> <segs.f32> <out.u8>
//       segs = N × (ax,ay,az, bx,by,bz). Ответ: N × u8, 1 — отрезок свободен в обе стороны (как rays_clear).
//       Для квадрантов (quads/bake_quads.py, 23.10): кто кого видит.
//
// Сборка: gcc -O3 -fopenmp -o rays rays.c -lm
// Библиотека для двойника (LuaJIT FFI, sim/): gcc -O3 -fPIC -shared -DRAYS_LIB -o librays.so rays.c -lm
//   int   rays_load(const char *cform)                       0 = ок; строит дерево
//   float rays_cast(ox,oy,oz, dx,dy,dz, range)                дистанция до стены или -1 (dir — единичный)
//   int   rays_clear(ax,ay,az, bx,by,bz)                      1 — отрезок a→b свободен (линия видимости)

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define EPS 0.0000100f
#define LEAF 4

typedef struct { float x, y, z; } V3;
typedef struct { uint32_t v[3]; uint32_t dummy; } TRI;
typedef struct { float lo[3], hi[3]; int32_t first, count; } NODE;  // count > 0 — лист [first, first+count)

static V3 *verts;
static TRI *tris;
static uint32_t nverts, ntris;
static uint32_t *order;   // перестановка треугольников под дерево
static NODE *bvh;
static int nbvh;
static float *cent;       // центроиды ×3

static void die(const char *m) { fprintf(stderr, "rays: %s\n", m); exit(1); }

static void load_cform(const char *path) {
	FILE *f = fopen(path, "rb");
	if (!f) die("нет cform");
	uint32_t hdr[3];
	float box[6];
	if (fread(hdr, 4, 3, f) != 3 || fread(box, 4, 6, f) != 6) die("короткий заголовок");
	if (hdr[0] != 4) die("cform не версии 4");
	nverts = hdr[1];
	ntris = hdr[2];
	verts = malloc(sizeof(V3) * nverts);
	tris = malloc(sizeof(TRI) * ntris);
	if (fread(verts, sizeof(V3), nverts, f) != nverts) die("вершины");
	if (fread(tris, sizeof(TRI), ntris, f) != ntris) die("треугольники");
	fclose(f);
}

// ---------- дерево (BVH): медианное деление по самой длинной оси центроидов ----------

static float ckey(uint32_t t, int ax) { return cent[t * 3 + ax]; }

static void nth(uint32_t *a, int lo, int hi, int k, int ax) {  // quickselect: a[k] на своём месте
	while (hi > lo) {
		float p = ckey(a[(lo + hi) / 2], ax);
		int i = lo, j = hi;
		while (i <= j) {
			while (ckey(a[i], ax) < p) i++;
			while (ckey(a[j], ax) > p) j--;
			if (i <= j) { uint32_t t = a[i]; a[i] = a[j]; a[j] = t; i++; j--; }
		}
		if (k <= j) hi = j; else if (k >= i) lo = i; else return;
	}
}

static int build(int lo, int hi) {  // [lo, hi)
	int me = nbvh++;
	NODE *n = &bvh[me];
	float clo[3] = {1e30f, 1e30f, 1e30f}, chi[3] = {-1e30f, -1e30f, -1e30f};
	for (int k = 0; k < 3; k++) { n->lo[k] = 1e30f; n->hi[k] = -1e30f; }
	for (int i = lo; i < hi; i++) {
		TRI *t = &tris[order[i]];
		for (int c = 0; c < 3; c++) {
			float *p = &verts[t->v[c]].x;
			for (int k = 0; k < 3; k++) {
				if (p[k] < n->lo[k]) n->lo[k] = p[k];
				if (p[k] > n->hi[k]) n->hi[k] = p[k];
			}
		}
		for (int k = 0; k < 3; k++) {
			float c = ckey(order[i], k);
			if (c < clo[k]) clo[k] = c;
			if (c > chi[k]) chi[k] = c;
		}
	}
	if (hi - lo <= LEAF) { n->first = lo; n->count = hi - lo; return me; }
	int ax = 0;
	for (int k = 1; k < 3; k++) if (chi[k] - clo[k] > chi[ax] - clo[ax]) ax = k;
	int mid = (lo + hi) / 2;
	nth(order, lo, hi - 1, mid, ax);
	int l = build(lo, mid);
	int r = build(mid, hi);
	bvh[me].first = l;   // внутренний узел: first = левый ребёнок,
	bvh[me].count = -r;  // count < 0, −count = правый (корень = 0, так что правый всегда > 0)
	return me;
}

static void build_bvh(void) {
	cent = malloc(sizeof(float) * 3 * ntris);
	order = malloc(sizeof(uint32_t) * ntris);
	for (uint32_t i = 0; i < ntris; i++) {
		order[i] = i;
		for (int k = 0; k < 3; k++)
			cent[i * 3 + k] = ((&verts[tris[i].v[0]].x)[k] + (&verts[tris[i].v[1]].x)[k] + (&verts[tris[i].v[2]].x)[k]) / 3.f;
	}
	bvh = malloc(sizeof(NODE) * (2 * ntris / LEAF + 64) * 2);
	nbvh = 0;
	build(0, ntris);
	free(cent);
}

// ---------- луч ----------

// Тест треугольника — дословно движковый _tri с bCull (xrCDB_ray.cpp:275)
static int tri_hit(const TRI *t, const float *pos, const float *dir, float *range) {
	const V3 *p0 = &verts[t->v[0]], *p1 = &verts[t->v[1]], *p2 = &verts[t->v[2]];
	float e1[3] = {p1->x - p0->x, p1->y - p0->y, p1->z - p0->z};
	float e2[3] = {p2->x - p0->x, p2->y - p0->y, p2->z - p0->z};
	float pv[3] = {dir[1] * e2[2] - dir[2] * e2[1], dir[2] * e2[0] - dir[0] * e2[2], dir[0] * e2[1] - dir[1] * e2[0]};
	float det = e1[0] * pv[0] + e1[1] * pv[1] + e1[2] * pv[2];
	if (det < EPS) return 0;
	float tv[3] = {pos[0] - p0->x, pos[1] - p0->y, pos[2] - p0->z};
	float u = tv[0] * pv[0] + tv[1] * pv[1] + tv[2] * pv[2];
	if (u < 0.f || u > det) return 0;
	float qv[3] = {tv[1] * e1[2] - tv[2] * e1[1], tv[2] * e1[0] - tv[0] * e1[2], tv[0] * e1[1] - tv[1] * e1[0]};
	float v = dir[0] * qv[0] + dir[1] * qv[1] + dir[2] * qv[2];
	if (v < 0.f || u + v > det) return 0;
	float r = (e2[0] * qv[0] + e2[1] * qv[1] + e2[2] * qv[2]) * (1.0f / det);
	*range = r;
	return 1;
}

static int box_hit(const NODE *n, const float *pos, const float *inv, float best, float *tnear) {
	float t0 = 0.f, t1 = best;
	for (int k = 0; k < 3; k++) {
		float a = (n->lo[k] - pos[k]) * inv[k], b = (n->hi[k] - pos[k]) * inv[k];
		if (a > b) { float s = a; a = b; b = s; }
		if (a > t0) t0 = a;
		if (b < t1) t1 = b;
		if (t0 > t1) return 0;
	}
	*tnear = t0;
	return 1;
}

// Ближайшее попадание: дистанция или -1; tri_out — номер треугольника
static float cast(const float *pos, const float *dir, float range, int32_t *tri_out) {
	float inv[3];
	for (int k = 0; k < 3; k++) inv[k] = dir[k] != 0.f ? 1.f / dir[k] : 1e30f;
	float best = range;
	int32_t best_t = -1;
	int stack[128], sp = 0;
	stack[sp++] = 0;
	while (sp) {
		const NODE *n = &bvh[stack[--sp]];
		float tn;
		if (!box_hit(n, pos, inv, best, &tn)) continue;
		if (n->count > 0) {
			for (int i = n->first; i < n->first + n->count; i++) {
				float r;
				if (tri_hit(&tris[order[i]], pos, dir, &r) && r > 0 && r <= best) {
					// движок: r > rRange отброшено, ближайшее с r < R.range
					if (best_t < 0 || r < best) { best = r; best_t = (int32_t)order[i]; }
				}
			}
		} else {
			int l = n->first, r = -n->count;
			float tl, tr;
			int hl = box_hit(&bvh[l], pos, inv, best, &tl), hr = box_hit(&bvh[r], pos, inv, best, &tr);
			if (hl && hr) {  // ближний ребёнок — последним в стек, проверим первым
				if (tl < tr) { stack[sp++] = r; stack[sp++] = l; } else { stack[sp++] = l; stack[sp++] = r; }
			} else if (hl) stack[sp++] = l;
			else if (hr) stack[sp++] = r;
		}
	}
	if (tri_out) *tri_out = best_t;
	return best_t < 0 ? -1.f : best;
}

static void *slurp(const char *path, size_t *n) {
	FILE *f = fopen(path, "rb");
	if (!f) die("не открыть вход");
	fseek(f, 0, SEEK_END);
	*n = ftell(f);
	fseek(f, 0, SEEK_SET);
	void *b = malloc(*n);
	if (fread(b, 1, *n, f) != *n) die("короткий вход");
	fclose(f);
	return b;
}

#ifdef RAYS_LIB
int rays_load(const char *path) {
	load_cform(path);
	build_bvh();
	return 0;
}

float rays_cast(float ox, float oy, float oz, float dx, float dy, float dz, float range) {
	float p[3] = {ox, oy, oz}, d[3] = {dx, dy, dz};
	return cast(p, d, range, NULL);
}

// Задние грани луч не ловит (как движок), поэтому стену «изнутри» он не видит. Для видимости между
// бойцами пускаем в обе стороны: стена между ними закрывает хотя бы один из двух лучей.
int rays_clear(float ax, float ay, float az, float bx, float by, float bz) {
	float d[3] = {bx - ax, by - ay, bz - az};
	float len = sqrtf(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
	if (len < 1e-4f) return 1;
	for (int k = 0; k < 3; k++) d[k] /= len;
	float a[3] = {ax, ay, az}, b[3] = {bx, by, bz}, back[3] = {-d[0], -d[1], -d[2]};
	return cast(a, d, len, NULL) < 0 && cast(b, back, len, NULL) < 0;
}
#else
int main(int argc, char **argv) {
	if (argc < 5) die("usage: rays pano|probe <cform> <in> <out> [ndirs range]");
	load_cform(argv[2]);
	build_bvh();
	fprintf(stderr, "rays: %u вершин, %u треугольников, %d узлов дерева\n", nverts, ntris, nbvh);

	size_t nb;
	float *in = slurp(argv[3], &nb);
	FILE *out = fopen(argv[4], "wb");
	if (!out) die("не открыть выход");

	if (!strcmp(argv[1], "pano")) {
		if (argc < 7) die("pano: нужны ndirs range");
		int nd = atoi(argv[5]);
		float range = atof(argv[6]);
		size_t np = nb / 12;
		uint16_t *res = malloc(sizeof(uint16_t) * np * nd);
		float (*dirs)[3] = malloc(sizeof(float) * 3 * nd);
		for (int i = 0; i < nd; i++) {
			double a = 2.0 * M_PI * i / nd;
			dirs[i][0] = (float)cos(a); dirs[i][1] = 0.f; dirs[i][2] = (float)sin(a);
		}
		#pragma omp parallel for schedule(dynamic, 256)
		for (size_t p = 0; p < np; p++) {
			for (int i = 0; i < nd; i++) {
				float d = cast(&in[p * 3], dirs[i], range, NULL);
				res[p * nd + i] = d < 0 ? 65535 : (uint16_t)fminf(65534.f, d * 100.f + 0.5f);
			}
		}
		fwrite(res, sizeof(uint16_t), np * nd, out);
		fprintf(stderr, "rays: pano %zu точек × %d направлений\n", np, nd);
	} else if (!strcmp(argv[1], "probe")) {
		size_t nr = nb / 28;
		for (size_t i = 0; i < nr; i++) {
			float *r = &in[i * 7];
			int32_t t;
			float d = cast(r, r + 3, r[6], &t);
			fwrite(&d, 4, 1, out);
			fwrite(&t, 4, 1, out);
		}
		fprintf(stderr, "rays: probe %zu лучей\n", nr);
	} else if (!strcmp(argv[1], "seg")) {
		size_t ns = nb / 24;
		uint8_t *res = malloc(ns);
		#pragma omp parallel for schedule(dynamic, 1024)
		for (size_t i = 0; i < ns; i++) {
			float *a = &in[i * 6], *b = a + 3;
			float d[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]};
			float len = sqrtf(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
			if (len < 1e-4f) { res[i] = 1; continue; }
			for (int k = 0; k < 3; k++) d[k] /= len;
			float back[3] = {-d[0], -d[1], -d[2]};
			res[i] = cast(a, d, len, NULL) < 0 && cast(b, back, len, NULL) < 0;
		}
		fwrite(res, 1, ns, out);
		fprintf(stderr, "rays: seg %zu отрезков\n", ns);
	} else die("режим pano, probe или seg");
	fclose(out);
	return 0;
}
#endif
