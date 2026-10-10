"""L'installateur des raccourcis GNOME : trois raccourcis (dicter, traduire, interrupteur) qui lancent `mya-key <mot>`.
Il ne touche qu'à ses propres entrées, détecte les conflits, ne remplace jamais un raccourci existant, et refuse tout
ce qui n'est pas une vraie combinaison de touches. Testé contre un faux `gsettings` qui garde son état dans un fichier."""
import ast, json, os, stat, subprocess, sys, tempfile, textwrap, unittest

BIN = os.path.join(os.path.dirname(__file__), "..", "bin")
TOOL = os.path.join(BIN, "mya_gnome_shortcuts.py")
MYA_KEY = os.path.realpath(os.path.join(BIN, "mya-key"))
MEDIA = "org.gnome.settings-daemon.plugins.media-keys"
LISTKEY = "custom-keybindings"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"

FAKE = textwrap.dedent('''\
    #!/usr/bin/env python3
    import ast, json, os, sys
    state_file = os.environ["FAKE_GSETTINGS_STATE"]
    st = json.load(open(state_file))
    st.setdefault("calls", []).append(sys.argv[1:])
    a = sys.argv[1:]
    MEDIA = "org.gnome.settings-daemon.plugins.media-keys"
    def save():
        json.dump(st, open(state_file, "w"))
    def gv(v):                       # représentation GVariant d'une chaîne
        return "'" + v.replace("\\\\", "\\\\\\\\").replace("'", "\\\\'") + "'"
    def parse(v):
        v = v.strip()
        if v.startswith("@as"):
            v = v[3:].strip()
        return ast.literal_eval(v)
    if a[:1] == ["list-recursively"]:
        for line in st.get("others", []):
            print(line)
        save(); sys.exit(0)
    if a[0] == "get" and a[1] == MEDIA and a[2] == "custom-keybindings":
        lst = st.get("list", [])
        print("@as []" if not lst else "[" + ", ".join(gv(p) for p in lst) + "]")
        save(); sys.exit(0)
    if a[0] == "set" and a[1] == MEDIA and a[2] == "custom-keybindings":
        st["list"] = parse(a[3]); save(); sys.exit(0)
    if len(a) >= 3 and a[1].startswith(MEDIA + ".custom-keybinding:"):
        path = a[1].split(":", 1)[1]
        key = a[2]
        slot = st.setdefault("keys", {}).setdefault(path, {})
        if a[0] == "get":
            print(gv(slot.get(key, ""))); save(); sys.exit(0)
        if a[0] == "set":
            slot[key] = parse(a[3]); save(); sys.exit(0)
        if a[0] == "reset":
            slot.pop(key, None); save(); sys.exit(0)
    save()
    print("fake gsettings: appel non géré: %r" % (a,), file=sys.stderr)
    sys.exit(1)
''')


class Fake:
    def __init__(self, others=(), custom=()):
        self.dir = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.dir.name, "state.json")
        bindir = os.path.join(self.dir.name, "bin")
        os.mkdir(bindir)
        exe = os.path.join(bindir, "gsettings")
        with open(exe, "w") as f:
            f.write(FAKE)
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IXUSR)
        keys = {p: dict(name=n, command=c, binding=b) for p, n, c, b in custom}
        json.dump({"list": [p for p, *_ in custom], "keys": keys, "others": list(others), "calls": []}, open(self.state, "w"))
        self.env = {**os.environ, "FAKE_GSETTINGS_STATE": self.state, "PATH": bindir + ":" + os.environ["PATH"]}

    def run(self, *args):
        return subprocess.run([sys.executable, TOOL, *args], env=self.env, capture_output=True, text=True, timeout=30)

    def st(self):
        return json.load(open(self.state))

    def calls(self):
        return self.st()["calls"]

    def close(self):
        self.dir.cleanup()


OTHERS = [
    "org.gnome.settings-daemon.plugins.media-keys terminal ['<Primary><Alt>t']",
    "org.gnome.desktop.wm.keybindings show-desktop ['<Primary><Super>d', '<Primary><Alt>d', '<Super>d']",
    "org.gnome.desktop.interface font-name 'Ubuntu 11'",
    "org.gnome.shell.keybindings toggle-message-tray ['<Super>v']",
]
SLUGS = ["mya-toggle", "mya-translate", "mya-lock"]


class Installation(unittest.TestCase):
    def setUp(self):
        self.f = Fake(others=OTHERS)

    def tearDown(self):
        self.f.close()

    def test_installe_trois_raccourcis_qui_lancent_mya_key(self):
        r = self.f.run("install")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.f.st()
        self.assertEqual(sorted(st["list"]), sorted(BASE + s + "/" for s in SLUGS))
        got = {s: st["keys"][BASE + s + "/"] for s in SLUGS}
        self.assertEqual(got["mya-toggle"]["binding"], "<Primary><Alt>m")
        self.assertEqual(got["mya-translate"]["binding"], "<Primary><Alt><Shift>m")
        self.assertEqual(got["mya-lock"]["binding"], "<Primary><Alt>k")
        for s, word in (("mya-toggle", "toggle"), ("mya-translate", "translate"), ("mya-lock", "lock")):
            self.assertEqual(got[s]["command"], f"{MYA_KEY} {word}")
            self.assertTrue(got[s]["name"].startswith("MYA "))

    def test_la_commande_installee_existe_et_est_executable(self):
        self.f.run("install")
        for s in SLUGS:
            cmd = self.f.st()["keys"][BASE + s + "/"]["command"].split()[0]
            self.assertTrue(os.access(cmd, os.X_OK), cmd)

    def test_idempotent(self):
        self.f.run("install")
        premier = self.f.st()
        r = self.f.run("install")
        self.assertEqual(r.returncode, 0)
        deuxieme = self.f.st()
        self.assertEqual(premier["list"], deuxieme["list"])
        self.assertEqual(premier["keys"], deuxieme["keys"])
        self.assertIn("already", r.stdout.lower())

    def test_ne_touche_qu_a_ses_propres_entrees(self):
        autre = (BASE + "custom0/", "Mon script", "/usr/bin/true", "<Primary><Alt>j")
        f = Fake(others=OTHERS, custom=[autre])
        try:
            f.run("install")
            st = f.st()
            self.assertEqual(st["list"][0], autre[0])
            self.assertEqual(st["keys"][autre[0]], {"name": "Mon script", "command": "/usr/bin/true", "binding": "<Primary><Alt>j"})
            self.assertEqual(len(st["list"]), 4)
        finally:
            f.close()

    def test_n_ecrit_que_dans_le_schema_des_raccourcis_personnalises(self):
        self.f.run("install")
        for call in self.f.calls():
            if call[0] in ("set", "reset"):
                self.assertTrue(call[1].startswith(MEDIA), call)

    def test_options_pour_choisir_ses_touches(self):
        r = self.f.run("install", "--toggle", "Pause", "--translate", "<Shift>Pause", "--lock", "<Primary><Alt>j")
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.f.st()["keys"]
        self.assertEqual(k[BASE + "mya-toggle/"]["binding"], "Pause")
        self.assertEqual(k[BASE + "mya-translate/"]["binding"], "<Shift>Pause")

    def test_changer_de_touche_met_a_jour_sans_dupliquer(self):
        self.f.run("install")
        self.f.run("install", "--toggle", "Pause")
        st = self.f.st()
        self.assertEqual(len(st["list"]), 3)
        self.assertEqual(st["keys"][BASE + "mya-toggle/"]["binding"], "Pause")

    def test_dry_run_ne_change_rien(self):
        r = self.f.run("install", "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertFalse([c for c in self.f.calls() if c[0] in ("set", "reset")])
        self.assertEqual(self.f.st()["list"], [])
        self.assertIn("<Primary><Alt>m", r.stdout)


class Conflits(unittest.TestCase):
    def tearDown(self):
        self.f.close()

    def test_une_touche_deja_prise_par_gnome_n_est_jamais_ecrasee(self):
        self.f = Fake(others=OTHERS)
        r = self.f.run("install", "--toggle", "<Primary><Alt>t")           # ouvre déjà le terminal
        self.assertEqual(r.returncode, 3)
        self.assertIn("terminal", r.stdout + r.stderr)
        st = self.f.st()
        self.assertNotIn(BASE + "mya-toggle/", st["list"])               # ce raccourci-là n'est pas installé
        self.assertIn(BASE + "mya-translate/", st["list"])               # les deux autres le sont

    def test_ordre_et_nom_des_modificateurs_ne_comptent_pas(self):
        self.f = Fake(others=OTHERS)
        for accel in ("<Alt><Primary>t", "<Control><Alt>t", "<Ctrl><Alt>T"):
            r = self.f.run("install", "--toggle", accel, "--dry-run")
            self.assertEqual(r.returncode, 3, accel)

    def test_conflit_avec_un_autre_raccourci_personnalise(self):
        autre = (BASE + "custom0/", "Mon script", "/usr/bin/true", "<Primary><Alt>m")
        self.f = Fake(others=OTHERS, custom=[autre])
        r = self.f.run("install")
        self.assertEqual(r.returncode, 3)
        self.assertIn("Mon script", r.stdout + r.stderr)
        self.assertEqual(self.f.st()["keys"][autre[0]]["binding"], "<Primary><Alt>m")

    def test_une_valeur_qui_n_est_pas_un_raccourci_ne_cree_pas_de_faux_conflit(self):
        self.f = Fake(others=OTHERS + ["org.gnome.desktop.interface font-name 'Pause'"])
        r = self.f.run("install", "--toggle", "Pause")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_un_texte_d_une_lettre_n_est_pas_un_raccourci(self):
        self.f = Fake(others=OTHERS + ["org.gnome.desktop.interface cursor-theme 'm'", "org.example.app unit 'k'"])
        r = self.f.run("install", "--toggle", "m", "--lock", "k")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_deux_raccourcis_identiques_demandes_refuses(self):
        self.f = Fake(others=OTHERS)
        r = self.f.run("install", "--toggle", "Pause", "--lock", "Pause")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.f.st()["list"], [])


class Validation(unittest.TestCase):
    def setUp(self):
        self.f = Fake(others=OTHERS)

    def tearDown(self):
        self.f.close()

    def test_combinaisons_invalides_refusees_avant_tout_appel_a_gsettings(self):
        for mauvaise in ("", "m'; rm -rf ~", "<Primary>", "<Primary> m", "<Primary><Alt>m;lock", "$(id)", "<Prim ary>m", "a" * 80, "<>m", "<Primary><Alt>é"):
            with self.subTest(mauvaise=mauvaise):
                r = self.f.run("install", "--toggle", mauvaise)
                self.assertEqual(r.returncode, 2)
        self.assertEqual(self.f.calls(), [])

    def test_commande_inconnue(self):
        self.assertEqual(self.f.run("frobnicate").returncode, 2)
        self.assertEqual(self.f.run().returncode, 2)

    def test_sans_gsettings_message_clair(self):
        env = {**os.environ, "PATH": "/nonexistent"}
        r = subprocess.run([sys.executable, TOOL, "install"], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 4)
        self.assertIn("gsettings", r.stderr)


class RetraitEtEtat(unittest.TestCase):
    def setUp(self):
        autre = (BASE + "custom0/", "Mon script", "/usr/bin/true", "<Primary><Alt>j")
        self.autre = autre
        self.f = Fake(others=OTHERS, custom=[autre])
        self.f.run("install")

    def tearDown(self):
        self.f.close()

    def test_remove_retire_les_siens_et_rien_d_autre(self):
        r = self.f.run("remove")
        self.assertEqual(r.returncode, 0)
        st = self.f.st()
        self.assertEqual(st["list"], [self.autre[0]])
        self.assertEqual(st["keys"][self.autre[0]]["binding"], "<Primary><Alt>j")
        for s in SLUGS:
            self.assertEqual(st["keys"].get(BASE + s + "/", {}), {})

    def test_remove_quand_rien_n_est_installe(self):
        self.f.run("remove")
        r = self.f.run("remove")
        self.assertEqual(r.returncode, 0)
        self.assertIn("nothing", r.stdout.lower())

    def test_status_montre_les_touches(self):
        r = self.f.run("status")
        self.assertEqual(r.returncode, 0)
        for accel in ("<Primary><Alt>m", "<Primary><Alt><Shift>m", "<Primary><Alt>k"):
            self.assertIn(accel, r.stdout)
        self.assertNotIn("Mon script", r.stdout)

    def test_status_quand_rien_n_est_installe(self):
        self.f.run("remove")
        self.assertIn("not installed", self.f.run("status").stdout.lower())

    def test_status_ne_modifie_rien(self):
        avant = self.f.st()
        self.f.run("status")
        apres = self.f.st()
        self.assertEqual(avant["list"], apres["list"])
        self.assertEqual(avant["keys"], apres["keys"])


if __name__ == "__main__":
    unittest.main()
