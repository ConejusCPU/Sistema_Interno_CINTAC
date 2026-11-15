import json

from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings

from .constants import TARIFAS_EJEMPLO
from .models import Tarifa, TramoContingencia, Usuario
from .services import calcular, cargar_tramos

CLAVE = "Inicial#2026"


def crear_usuario(username, rol="Analista", clave=CLAVE, primer_ingreso=False, **kw):
    u = Usuario(username=username, nombre=f"Nombre {username}", rol=rol,
                primer_ingreso=primer_ingreso, **kw)
    u.set_password(clave)
    u.save()
    return u


class BaseApi(TestCase):
    def setUp(self):
        for e, o, d, c, m, dias in TARIFAS_EJEMPLO:
            Tarifa.objects.create(embarcador=e, origen=o, destino=d, cobro=c, monto=m, dias=dias)
        self.admin = crear_usuario("admin", "Administrador")
        self.analista = crear_usuario("analista", "Analista")
        self.c = Client()

    def post(self, url, datos=None, cliente=None):
        return (cliente or self.c).post(url, json.dumps(datos or {}), content_type="application/json")

    def delete(self, url):
        return self.c.delete(url)

    def entrar(self, usuario, clave=CLAVE):
        r = self.post("/api/login/", {"usuario": usuario, "clave": clave})
        self.assertEqual(r.status_code, 200, r.content)
        return r


class CalculoTests(BaseApi):
    def datos(self, **kw):
        base = {"tarifaId": Tarifa.objects.get(embarcador="Maersk", origen="Shanghai").pk,
                "toneladas": 60, "contenedores": 0, "fob": 85000, "dias": 32, "tlc": False, "tc": 950}
        base.update(kw)
        return base

    def test_cotizacion_sin_tlc(self):
        self.entrar("analista")
        r = self.post("/api/cotizar/", self.datos()).json()["resultado"]
        # 3 contenedores x 2850 = 8550; +5% (32 días) = 8977,5; CIF = 93977,5
        self.assertEqual(r["contUsados"], 3)
        self.assertAlmostEqual(r["fleteBase"], 8550)
        self.assertAlmostEqual(r["pctCont"], 0.05)
        self.assertAlmostEqual(r["cif"], 93977.5)
        self.assertAlmostEqual(r["arancel"], 93977.5 * 0.06)
        self.assertAlmostEqual(r["iva"], 93977.5 * 0.19)
        self.assertAlmostEqual(r["totalUSD"], 93977.5 * 1.25)
        self.assertAlmostEqual(r["totalCLP"], 93977.5 * 1.25 * 950)

    def test_tlc_arancel_cero(self):
        self.entrar("analista")
        r = self.post("/api/cotizar/", self.datos(tlc=True)).json()["resultado"]
        self.assertEqual(r["arancel"], 0)

    def test_cobro_por_tonelada(self):
        self.entrar("analista")
        t = Tarifa.objects.get(cobro="tonelada")
        r = self.post("/api/cotizar/", self.datos(tarifaId=t.pk, dias=42)).json()["resultado"]
        self.assertAlmostEqual(r["fleteBase"], 118 * 60)
        self.assertAlmostEqual(r["pctCont"], 0.08)

    def test_tramos_por_dias(self):
        tramos = cargar_tramos()
        t = Tarifa.objects.first()
        for dias, esperado in [(1, 0.03), (30, 0.03), (31, 0.05), (40, 0.05), (41, 0.08), (90, 0.08)]:
            self.assertEqual(calcular(t, 10, 0, 0, dias, False, 1, tramos)["pctCont"], esperado)

    def test_margen_editable(self):
        TramoContingencia.objects.filter(dias_hasta=30).update(porcentaje="4.50")
        self.entrar("analista")
        r = self.post("/api/cotizar/", self.datos(dias=20)).json()["resultado"]
        self.assertAlmostEqual(r["pctCont"], 0.045)

    def test_sin_tramos_usa_valores_por_defecto(self):
        TramoContingencia.objects.all().delete()
        self.assertEqual(calcular(Tarifa.objects.first(), 10, 0, 0, 35, False, 1)["pctCont"], 0.05)

    def test_solo_un_tramo_sin_limite(self):
        with self.assertRaises(ValidationError):
            TramoContingencia(dias_hasta=None, porcentaje="9").full_clean()

    def test_entradas_invalidas(self):
        self.entrar("analista")
        for malo in ({"toneladas": -1}, {"fob": "abc"}, {"dias": float("inf")}, {"tarifaId": 99999}):
            r = self.post("/api/cotizar/", self.datos(**malo))
            self.assertIn(r.status_code, (400, 404), malo)

    def test_comparador_ordenado(self):
        self.entrar("analista")
        r = self.post("/api/comparar/", {"ruta": "Shanghai → San Antonio", "toneladas": 60,
                                         "fob": 85000, "tc": 950, "tlc": False}).json()["resultados"]
        totales = [x["totalUSD"] for x in r]
        self.assertEqual(len(r), 3)
        self.assertEqual(totales, sorted(totales))
        self.assertEqual(r[0]["tarifa"]["embarcador"], "MSC")

    def test_calculo_requiere_sesion(self):
        self.assertEqual(self.post("/api/cotizar/", self.datos()).status_code, 401)


class LoginTests(BaseApi):
    def test_bloqueo_tras_tres_intentos(self):
        r = self.post("/api/login/", {"usuario": "analista", "clave": "mala"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("quedan 2 intentos", r.json()["error"])
        self.assertIn("queda 1 intento", self.post("/api/login/", {"usuario": "analista", "clave": "mala"}).json()["error"])
        r = self.post("/api/login/", {"usuario": "analista", "clave": "mala"})
        self.assertIn("bloqueada", r.json()["error"])
        r = self.post("/api/login/", {"usuario": "analista", "clave": CLAVE})
        self.assertEqual(r.status_code, 423)              # bloqueada aunque la clave sea correcta

    def test_usuario_inexistente_mensaje_generico(self):
        r = self.post("/api/login/", {"usuario": "nadie", "clave": "x"})
        self.assertEqual(r.json()["error"], "Usuario o contraseña incorrectos.")

    def test_login_ignora_mayusculas_y_reinicia_intentos(self):
        self.post("/api/login/", {"usuario": "analista", "clave": "mala"})
        self.entrar("ANALISTA")
        self.analista.refresh_from_db()
        self.assertEqual(self.analista.intentos_fallidos, 0)

    def test_primer_ingreso_exige_cambio(self):
        crear_usuario("nuevo", primer_ingreso=True)
        r = self.entrar("nuevo")
        self.assertTrue(r.json()["requiereCambioClave"])
        self.assertEqual(self.c.get("/api/tarifas/").status_code, 401)       # aún sin sesión de trabajo
        peticion = lambda a, b: self.post("/api/cambiar-clave/", {"clave1": a, "clave2": b})
        self.assertIn("no cumple el estándar", peticion("corta", "corta").json()["error"])
        self.assertIn("no coinciden", peticion("Nueva#Clave1", "Nueva#Clave2").json()["error"])
        self.assertIn("distinta", peticion(CLAVE, CLAVE).json()["error"])
        r = peticion("Nueva#Clave1", "Nueva#Clave1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/api/tarifas/").status_code, 200)
        self.assertFalse(Usuario.objects.get(username="nuevo").primer_ingreso)

    def test_cambio_de_clave_sin_login_previo(self):
        r = self.post("/api/cambiar-clave/", {"clave1": "Nueva#Clave1", "clave2": "Nueva#Clave1"})
        self.assertEqual(r.status_code, 401)

    def test_sesion_y_logout(self):
        self.assertFalse(self.c.get("/api/sesion/").json()["autenticado"])
        self.entrar("analista")
        self.assertTrue(self.c.get("/api/sesion/").json()["autenticado"])
        self.post("/api/logout/")
        self.assertFalse(self.c.get("/api/sesion/").json()["autenticado"])

    def test_csrf_obligatorio(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post("/api/login/", json.dumps({"usuario": "analista", "clave": CLAVE}),
                   content_type="application/json")
        self.assertEqual(r.status_code, 403)


class PermisosYMantenedores(BaseApi):
    def test_analista_no_administra(self):
        self.entrar("analista")
        self.assertEqual(self.c.get("/api/tarifas/").status_code, 200)
        self.assertEqual(self.post("/api/tarifas/", {}).status_code, 403)
        self.assertEqual(self.post("/api/tarifas/restaurar/").status_code, 403)
        self.assertEqual(self.delete(f"/api/tarifas/{Tarifa.objects.first().pk}/").status_code, 403)
        self.assertEqual(self.c.get("/api/usuarios/").status_code, 403)
        self.assertEqual(self.post("/api/usuarios/", {"nombre": "x", "usuario": "y", "rol": "Analista"}).status_code, 403)
        self.assertEqual(self.delete(f"/api/usuarios/{self.admin.pk}/").status_code, 403)
        self.assertEqual(self.post(f"/api/usuarios/{self.admin.pk}/restablecer/").status_code, 403)
        self.assertEqual(self.post(f"/api/usuarios/{self.analista.pk}/desbloquear/").status_code, 403)

    def test_tarifas_crud(self):
        self.entrar("admin")
        n = Tarifa.objects.count()
        ok = {"embarcador": "ONE", "origen": "Busan", "destino": "San Antonio", "cobro": "contenedor",
              "monto": 2500.5, "dias": 33}
        r = self.post("/api/tarifas/", ok)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Tarifa.objects.count(), n + 1)
        for malo in ({"monto": 0}, {"dias": 0}, {"embarcador": " "}, {"cobro": "otro"}, {"monto": "x"}):
            self.assertEqual(self.post("/api/tarifas/", {**ok, **malo}).status_code, 400, malo)
        nueva = Tarifa.objects.get(embarcador="ONE")
        self.assertEqual(self.delete(f"/api/tarifas/{nueva.pk}/").status_code, 200)
        self.post("/api/tarifas/restaurar/")
        self.assertEqual(Tarifa.objects.count(), len(TARIFAS_EJEMPLO))

    def test_crear_usuario_y_reglas(self):
        self.entrar("admin")
        r = self.post("/api/usuarios/", {"nombre": "María Pérez", "usuario": "mperez@cintac.cl", "rol": "Analista"})
        self.assertEqual(r.status_code, 200)
        temporal = r.json()["temporal"]["clave"]
        u = Usuario.objects.get(username="mperez@cintac.cl")
        self.assertTrue(u.primer_ingreso)
        self.assertTrue(u.check_password(temporal))
        self.assertNotEqual(u.password, temporal)                       # nunca en texto plano
        casos = [({"usuario": "MPEREZ@cintac.cl"}, "ya existe"), ({"usuario": "con espacio"}, "espacios"),
                 ({"usuario": "a@b"}, "formato"), ({"rol": "Root"}, "rol válido"), ({"nombre": ""}, "Completa")]
        base = {"nombre": "X", "usuario": "otro", "rol": "Analista"}
        for cambio, texto in casos:
            r = self.post("/api/usuarios/", {**base, **cambio})
            self.assertEqual(r.status_code, 400, cambio)
            self.assertIn(texto, r.json()["error"])

    def test_no_eliminar_a_si_mismo_ni_al_ultimo_admin(self):
        self.entrar("admin")
        self.assertEqual(self.delete(f"/api/usuarios/{self.admin.pk}/").status_code, 400)
        otro = crear_usuario("admin2", "Administrador")
        self.assertEqual(self.delete(f"/api/usuarios/{otro.pk}/").status_code, 200)
        self.assertEqual(self.delete(f"/api/usuarios/{self.analista.pk}/").status_code, 200)

    def test_restablecer_y_desbloquear(self):
        self.entrar("admin")
        self.analista.bloqueado = True
        self.analista.intentos_fallidos = 3
        self.analista.save()
        self.post(f"/api/usuarios/{self.analista.pk}/desbloquear/")
        r = self.post(f"/api/usuarios/{self.analista.pk}/restablecer/")
        self.analista.refresh_from_db()
        self.assertFalse(self.analista.bloqueado)
        self.assertTrue(self.analista.primer_ingreso)
        self.assertTrue(self.analista.check_password(r.json()["temporal"]["clave"]))
        self.assertEqual(self.post(f"/api/usuarios/{self.admin.pk}/restablecer/").status_code, 400)

    def test_restaurar_usuarios_deshabilitado_por_defecto(self):
        self.entrar("admin")
        self.assertEqual(self.post("/api/usuarios/restaurar/").status_code, 403)
        self.assertEqual(Usuario.objects.count(), 2)

    @override_settings(PERMITIR_RESTAURAR_USUARIOS_EJEMPLO=True)
    def test_restaurar_usuarios_habilitado(self):
        self.entrar("admin")
        r = self.post("/api/usuarios/restaurar/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sorted(u.username for u in Usuario.objects.all()),
                         ["admin", "admin_cintac", "analista1", "analista2"])
        self.assertEqual(len(r.json()["temporales"]), 3)

    def test_rol_administrador_da_acceso_a_django_admin(self):
        self.assertTrue(self.admin.is_staff and self.admin.is_superuser)
        self.assertFalse(self.analista.is_staff or self.analista.is_superuser)
        a = Client()
        a.force_login(self.admin)
        self.assertEqual(a.get("/admin/cotizador/tramocontingencia/").status_code, 200)
        b = Client()
        b.force_login(self.analista)
        self.assertEqual(b.get("/admin/cotizador/tramocontingencia/").status_code, 302)


class PaginaTests(TestCase):
    def test_pagina_principal_y_salud(self):
        c = Client()
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("csrftoken", r.cookies)
        self.assertContains(r, "Cotizador Interno de Fletes de Importación")
        self.assertEqual(c.get("/salud/").content, b"ok")
