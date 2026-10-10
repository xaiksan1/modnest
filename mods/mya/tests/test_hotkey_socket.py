"""hotkey.py en mode « socket » (Wayland) : aucune touche n'est lue. GNOME détecte la combinaison de touches et lance
`mya-key <mot>`, qui dépose le mot dans un socket privé ; l'assistant n'imprime que TOGGLE, TRANSLATE ou LOCK."""
import os, signal, socket, stat, subprocess, sys, tempfile, threading, time, unittest

BIN = os.path.join(os.path.dirname(__file__), "..", "bin")
HOTKEY = os.path.join(BIN, "hotkey.py")
MYA_KEY = os.path.join(BIN, "mya-key")


class Helper:
    """Lance hotkey.py en mode socket et lit ses lignes sans jamais bloquer le test."""

    def __init__(self, extra_env=None, mode="socket"):
        self.dir = tempfile.TemporaryDirectory()
        self.sock = os.path.join(self.dir.name, "k.sock")
        self.fake_dir = os.path.join(self.dir.name, "bin")
        os.mkdir(self.fake_dir)
        self.marker = os.path.join(self.dir.name, "xinput-a-ete-appele")
        fake = os.path.join(self.fake_dir, "xinput")
        with open(fake, "w") as f:
            f.write(f"#!/bin/sh\ntouch {self.marker}\n")
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
        env = {**os.environ, "MYA_HOTKEY_MODE": mode, "MYA_HOTKEY_SOCKET": self.sock,
               "PATH": self.fake_dir + ":" + os.environ["PATH"], **(extra_env or {})}
        self.p = subprocess.Popen([sys.executable, HOTKEY], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        self.lines, self._t = [], threading.Thread(target=self._read, daemon=True)
        self._t.start()

    def _read(self):
        for line in self.p.stdout:
            self.lines.append(line.rstrip("\n"))

    def wait_ready(self, timeout=8):
        fin = time.time() + timeout
        while time.time() < fin:
            if os.path.exists(self.sock) and self.p.poll() is None:
                try:
                    with socket.socket(socket.AF_UNIX) as s:
                        s.connect(self.sock)
                    return True
                except OSError:
                    pass
            time.sleep(0.05)
        return False

    def say(self, brut, timeout=3):
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(timeout)
            s.connect(self.sock)
            s.sendall(brut if isinstance(brut, bytes) else (brut + "\n").encode())
            try:
                return s.recv(64).decode(errors="replace").strip()
            except socket.timeout:
                return "(délai)"

    def words(self, attendre=0.4):
        time.sleep(attendre)
        return [l for l in self.lines if l and not l.startswith(("MODE", "ERR"))]

    def close(self):
        if self.p.poll() is None:
            self.p.send_signal(signal.SIGTERM)
            try:
                self.p.wait(5)
            except subprocess.TimeoutExpired:
                self.p.kill()
        self.p.stdout.close()
        self.p.stderr.close()
        self.dir.cleanup()


class Socket(unittest.TestCase):
    def setUp(self):
        self.h = Helper()
        self.assertTrue(self.h.wait_ready(), "l'assistant n'a pas démarré")

    def tearDown(self):
        self.h.close()

    def test_il_annonce_son_mode_et_n_appelle_jamais_xinput(self):
        time.sleep(0.3)
        self.assertIn("MODE\tsocket", self.h.lines)
        self.assertFalse(os.path.exists(self.h.marker), "xinput a été lancé : une touche pourrait être lue")

    def test_le_socket_est_prive(self):
        self.assertEqual(stat.S_IMODE(os.stat(self.h.sock).st_mode), 0o600)

    def test_les_trois_mots(self):
        for brut, mot in (("toggle", "TOGGLE"), ("translate", "TRANSLATE"), ("lock", "LOCK")):
            self.assertEqual(self.h.say(brut), "ok")
        self.assertEqual(self.h.words(), ["TOGGLE", "TRANSLATE", "LOCK"])

    def test_majuscules_et_espaces_tolerés(self):
        self.assertEqual(self.h.say("  Toggle \r"), "ok")
        self.assertEqual(self.h.words(), ["TOGGLE"])

    def test_tout_le_reste_est_refuse_et_n_imprime_rien(self):
        for mauvais in ("", "TOGGLE2", "toggle toggle", "rm -rf ~", "toggle; lock", "\x00toggle", "ESC", "a" * 500, "translate\nlock"):
            self.assertEqual(self.h.say(mauvais), "no", repr(mauvais[:20]))
        self.assertEqual(self.h.say(b"\xff\xfe\xfd\n"), "no")
        for brut in (b"tog\xc3\xa9gle\n", b"to\xffggle\n", b"toggle\xe2\x80\x8b\n"):      # un octet non ASCII dans un mot valide : refusé, pas « nettoyé »
            self.assertEqual(self.h.say(brut), "no", brut)
        self.assertEqual(self.h.words(), [])

    def test_une_connexion_qui_ne_dit_rien_ne_bloque_personne(self):
        lent = socket.socket(socket.AF_UNIX)
        lent.connect(self.h.sock)
        debut = time.time()
        self.assertEqual(self.h.say("toggle"), "ok")
        self.assertLess(time.time() - debut, 3)
        lent.close()
        self.assertEqual(self.h.words(), ["TOGGLE"])

    def test_un_flot_sans_fin_est_coupe(self):
        self.assertEqual(self.h.say(b"x" * 100_000), "no")
        self.assertEqual(self.h.say("toggle"), "ok")

    def test_arret_propre_retire_le_socket(self):
        self.h.p.send_signal(signal.SIGTERM)
        self.assertEqual(self.h.p.wait(5), 0)
        self.assertFalse(os.path.exists(self.h.sock))


class Demarrage(unittest.TestCase):
    def test_un_deuxieme_assistant_refuse_au_lieu_de_voler_le_socket(self):
        a = Helper()
        try:
            self.assertTrue(a.wait_ready())
            env = {**os.environ, "MYA_HOTKEY_MODE": "socket", "MYA_HOTKEY_SOCKET": a.sock}
            r = subprocess.run([sys.executable, HOTKEY], env=env, capture_output=True, text=True, timeout=15)
            self.assertIn("ERR\talready running", r.stdout)
            self.assertEqual(a.say("toggle"), "ok")                  # le premier fonctionne toujours
        finally:
            a.close()

    def test_un_vieux_socket_sans_ecoute_est_remplace(self):
        d = tempfile.TemporaryDirectory()
        sock = os.path.join(d.name, "k.sock")
        orphelin = socket.socket(socket.AF_UNIX)
        orphelin.bind(sock)
        orphelin.close()                                              # le fichier reste, personne n'écoute
        self.assertTrue(os.path.exists(sock))
        h = Helper(extra_env={"MYA_HOTKEY_SOCKET": sock})
        h.sock = sock                                                  # c'est CE chemin-là, celui de l'orphelin, qu'il faut surveiller
        try:
            self.assertTrue(h.wait_ready(), "le vieux socket n'a pas été remplacé")
            self.assertEqual(h.say("toggle"), "ok")
            self.assertEqual(h.words(), ["TOGGLE"])
        finally:
            h.close()
            d.cleanup()

    def test_sans_dossier_d_execution_et_sans_chemin_l_assistant_refuse(self):
        env = {k: v for k, v in os.environ.items() if k not in ("XDG_RUNTIME_DIR", "MYA_HOTKEY_SOCKET")}
        env["MYA_HOTKEY_MODE"] = "socket"
        r = subprocess.run([sys.executable, HOTKEY], env=env, capture_output=True, text=True, timeout=15)
        self.assertIn("ERR\tno runtime dir", r.stdout)

    def test_mode_auto_choisit_socket_sous_wayland_et_xinput_sous_x11(self):
        d = tempfile.TemporaryDirectory()
        sock = os.path.join(d.name, "k.sock")
        env = {**os.environ, "MYA_HOTKEY_SOCKET": sock, "XDG_SESSION_TYPE": "wayland"}
        env.pop("MYA_HOTKEY_MODE", None)
        p = subprocess.Popen([sys.executable, HOTKEY], env=env, stdout=subprocess.PIPE, text=True)
        try:
            fin = time.time() + 8
            while not os.path.exists(sock) and time.time() < fin:
                time.sleep(0.05)
            self.assertTrue(os.path.exists(sock))
        finally:
            p.terminate()
            p.wait(5)
            p.stdout.close()
        env["XDG_SESSION_TYPE"] = "x11"
        env["PATH"] = d.name                                          # aucun xinput : le mode X11 doit le dire
        r = subprocess.run([sys.executable, HOTKEY], env=env, capture_output=True, text=True, timeout=15)
        self.assertIn("ERR\txinput not found", r.stdout)
        d.cleanup()


class Client(unittest.TestCase):
    def run_key(self, *args, sock=None, env_extra=None):
        env = {**os.environ, **({"MYA_HOTKEY_SOCKET": sock} if sock else {}), **(env_extra or {})}
        return subprocess.run([sys.executable, MYA_KEY, *args], env=env, capture_output=True, text=True, timeout=15)

    def test_le_client_depose_le_mot(self):
        h = Helper()
        try:
            self.assertTrue(h.wait_ready())
            r = self.run_key("toggle", sock=h.sock)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(h.words(), ["TOGGLE"])
        finally:
            h.close()

    def test_le_client_dit_clairement_quand_mya_ne_tourne_pas(self):
        d = tempfile.TemporaryDirectory()
        r = self.run_key("toggle", sock=os.path.join(d.name, "absent.sock"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("MYA", r.stderr)
        d.cleanup()

    def test_le_client_refuse_les_mots_inconnus_sans_se_connecter(self):
        for args in (("rm",), ("toggle", "lock"), (), ("TOGGLE;",)):
            r = self.run_key(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("usage", r.stderr.lower())

    def test_le_client_est_executable_et_a_un_shebang(self):
        self.assertTrue(os.access(MYA_KEY, os.X_OK))
        with open(MYA_KEY) as f:
            self.assertTrue(f.readline().startswith("#!"))


if __name__ == "__main__":
    unittest.main()
