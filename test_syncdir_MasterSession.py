import abc
import copy
import io
import os
import stat
import syncdir
import sys
import tempfile
import unittest

TIMEVAL1 = 1234567890
TIMEVAL2 = 1234567895
if sys.platform == "linux":
    TIMESTR1 = " 9 Sat Feb 14 00:31:30 2009"
    TIMESTR2 = " 9 Sat Feb 14 00:31:35 2009"
else:
    TIMESTR1 = "10 Sat Feb 14 00:31:30 2009"
    TIMESTR2 = "10 Sat Feb 14 00:31:35 2009"

class Params:
    pass

class MasterSessionTestCase(unittest.TestCase, metaclass=abc.ABCMeta):
    def __init__(self, params : Params):
        if isinstance(params, Params):
            # Real test case, explicitly created in load_tests.
            unittest.TestCase.__init__(self, "runTest")
            self.params = copy.copy(params)
        else:
            # Despite the presence of load_tests, unittest/suite instantiates
            # one with a methodName argument for each class, but (luckily)
            # never tries to run them (at least in python 3.4.3), even if
            # we invoke the base constructor. Shrugs shoulders.
            pass
    def setUp(self):
        self.src = tempfile.TemporaryDirectory(prefix="test_syncdir_", suffix=".lhs")
        self.dst = tempfile.TemporaryDirectory(prefix="test_syncdir_", suffix=".rhs")
        self.out = io.StringIO()
    def tearDown(self):
        self.dst.cleanup()
        self.src.cleanup()
        self.out.close()
    def runTest(self):
        class TestChooser:
            def __init__(self, answers, out):
                self.answers = answers
                self.out = out
                self.prompts = 0
            def ask(self, prompt):
                self.out.write(prompt + "\n")
                self.prompts += 1
                if self.prompts > len(self.answers):
                    raise RuntimeError('Starved for answers after %i prompts, at "%s"' % (self.prompts, prompt))
                return self.answers[self.prompts-1]
        chooser = TestChooser(answers=self.params.answers, out=self.out)
        with self.subTest(clean=self.params.clean, do_nothing=self.params.do_nothing, do_everything=self.params.do_everything, follow_link=self.params.follow_link, ignore_time=self.params.ignore_time, trust_time=self.params.trust_time, answers=self.params.answers):
            syncdir.MasterSession(self.src.name, self.dst.name, chooser=chooser, out=self.out, clean=self.params.clean, do_nothing=self.params.do_nothing, do_everything=self.params.do_everything, follow_link=self.params.follow_link, ignore_time=self.params.ignore_time, trust_time=self.params.trust_time).run()
            self.assertEqual(chooser.prompts, len(self.params.answers))
            self.check()
    @abc.abstractmethod
    def check(self):
        pass
    def affirmative(self):
        return self.params.do_everything or (self.params.answers and self.params.answers[0] in ['y', 'Y', 'A'])

class MasterSessionTestCase_empty(MasterSessionTestCase):
    def check(self):
        self.assertEqual(self.out.getvalue(), "")
        for folder in self.src, self.dst:
            self.assertEqual(os.listdir(folder.name), [])

class MasterSessionTestCase_2_files_identical(MasterSessionTestCase):
    def setUp(self):
        super().setUp()
        for folder in self.src, self.dst:
            with open(os.path.join(folder.name, "phile"), "w") as f:
                f.write("contents\n")
        self._check_folders(cleaned=False)
    def check(self):
        if self.params.clean:
            self.assertEqual(self.out.getvalue()[:29], "phile has not changed, remove")
        else:
            self.assertEqual(self.out.getvalue(), "\rphile has not changed")
        cleaned = self.affirmative() and self.params.clean
        self._check_folders(cleaned=cleaned)
    def _check_folders(self, cleaned):
        if cleaned:
            self.assertEqual(os.listdir(self.src.name), [])
        else:
            self.assertEqual(os.listdir(self.src.name), ["phile"])
        self.assertEqual(os.listdir(self.dst.name), ["phile"])

class MasterSessionTestCase_2_files_same_name_size_time(MasterSessionTestCase):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.src.name, "phile"), "w") as f:
            f.write("lhs contents\n")
        with open(os.path.join(self.dst.name, "phile"), "w") as f:
            f.write("rhs contents\n") # same file size as src file
        for folder in self.src, self.dst:
            os.utime(os.path.join(folder.name, "phile"), (TIMEVAL1,TIMEVAL1))
        self._check_folders(cleaned=False, copied=False)
    def check(self):
        if self.params.trust_time:
            if self.params.clean:
                self.assertEqual(self.out.getvalue()[:29], "phile has not changed, remove")
            else:
                self.assertEqual(self.out.getvalue(), "\rphile has not changed")
        else:
            out = self.out.getvalue().split('\n\n')
            self.assertEqual(len(out), 2)
            self.assertEqual(out[0], "\rphile  - difference:\n- lhs contents\n? ^\n+ rhs contents\n? ^")
            if self.params.clean:
                self.assertEqual(out[1][:34], "phile has changed as shown, remove")
            else:
                self.assertEqual(out[1][:37], "phile has changed as shown, overwrite")
        cleaned = self.affirmative() and self.params.clean
        copied = self.affirmative() and not self.params.clean and not self.params.trust_time
        self._check_folders(cleaned=cleaned, copied=copied)
    def _check_folders(self, cleaned, copied):
        if cleaned:
            self.assertEqual(os.listdir(self.src.name), [])
        else:
            self.assertEqual(os.listdir(self.src.name), ["phile"])
            with open(os.path.join(self.src.name, "phile"), "r") as f:
                self.assertEqual(f.read(), "lhs contents\n")
        self.assertEqual(os.listdir(self.dst.name), ["phile"])
        with open(os.path.join(self.dst.name, "phile"), "r") as f:
            if copied:
                self.assertEqual(f.read(), "lhs contents\n")
            else:
                self.assertEqual(f.read(), "rhs contents\n")

class MasterSessionTestCase_2_files_same_name_size(MasterSessionTestCase):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.src.name, "phile"), "w") as f:
            f.write("lhs contents\n")
        with open(os.path.join(self.dst.name, "phile"), "w") as f:
            f.write("rhs contents\n") # same file size as src file
        os.utime(os.path.join(self.src.name, "phile"), (TIMEVAL1,TIMEVAL1))
        self._check_folders(cleaned=False, copied=False)
    def check(self):
        out = self.out.getvalue().split('\n\n')
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], "\rphile  - difference:\n- lhs contents\n? ^\n+ rhs contents\n? ^")
        if self.params.clean:
            self.assertEqual(out[1][:34], "phile has changed as shown, remove")
        else:
            self.assertEqual(out[1][:37], "phile has changed as shown, overwrite")
        cleaned = self.affirmative() and self.params.clean
        copied = self.affirmative() and not self.params.clean
        self._check_folders(cleaned=cleaned, copied=copied)
    def _check_folders(self, cleaned, copied):
        if cleaned:
            self.assertEqual(os.listdir(self.src.name), [])
        else:
            self.assertEqual(os.listdir(self.src.name), ["phile"])
            with open(os.path.join(self.src.name, "phile"), "r") as f:
                self.assertEqual(f.read(), "lhs contents\n")
        self.assertEqual(os.listdir(self.dst.name), ["phile"])
        with open(os.path.join(self.dst.name, "phile"), "r") as f:
            if copied:
                self.assertEqual(f.read(), "lhs contents\n")
            else:
                self.assertEqual(f.read(), "rhs contents\n")

class MasterSessionTestCase_2_files_same_name_contents(MasterSessionTestCase):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.src.name, "phile"), "w") as f:
            f.write("contents\n")
        with open(os.path.join(self.dst.name, "phile"), "w") as f:
            f.write("contents\n")
        os.utime(os.path.join(self.src.name, "phile"), (TIMEVAL1,TIMEVAL1))
        os.utime(os.path.join(self.dst.name, "phile"), (TIMEVAL2,TIMEVAL2))
        self._check_folders(cleaned=False, touched=False)
    def check(self):
        if self.params.ignore_time:
            if self.params.clean:
                self.assertEqual(self.out.getvalue()[:29], "phile has not changed, remove")
            else:
                self.assertEqual(self.out.getvalue(), "\rphile has not changed")
        else:
            out = self.out.getvalue().split('\n')
            self.assertEqual(out[0], "        %s %s" % (TIMESTR1, self.src.name))
            self.assertEqual(out[1], "        %s %s" % (TIMESTR2, self.dst.name))
            if self.params.do_everything or self.params.do_nothing:
                if self.params.clean:
                    self.assertEqual(out[2], "phile has different time, remove")
                else:
                    self.assertEqual(out[2], "phile has different time, touch")
            else:
                if self.params.clean:
                    self.assertEqual(out[2], "phile has different time, remove? [yes no AllYes ZeroYes Quit] n\b")
                else:
                    self.assertEqual(out[2], "phile has different time, touch? [yes no AllYes ZeroYes Quit] n\b")
            self.assertEqual(out[3], "")
            self.assertEqual(len(out), 4)
        cleaned = self.affirmative() and self.params.clean
        touched = self.affirmative() and not self.params.clean and not self.params.ignore_time
        self._check_folders(cleaned=cleaned, touched=touched)
    def _check_folders(self, cleaned, touched):
        if cleaned:
            self.assertEqual(os.listdir(self.src.name), [])
        else:
            self.assertEqual(os.listdir(self.src.name), ["phile"])
            with open(os.path.join(self.src.name, "phile"), "r") as f:
                self.assertEqual(f.read(), "contents\n")
            self.assertEqual(os.stat(os.path.join(self.src.name, "phile"))[stat.ST_MTIME], TIMEVAL1)
        self.assertEqual(os.listdir(self.dst.name), ["phile"])
        with open(os.path.join(self.dst.name, "phile"), "r") as f:
            self.assertEqual(f.read(), "contents\n")
        if touched:
            self.assertEqual(os.stat(os.path.join(self.dst.name, "phile"))[stat.ST_MTIME], TIMEVAL1)
        else:
            self.assertEqual(os.stat(os.path.join(self.dst.name, "phile"))[stat.ST_MTIME], TIMEVAL2)

class MasterSessionTestCase_2_different_files(MasterSessionTestCase):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.src.name, "lhs phile"), "w") as f:
            f.write("lhs contents\n")
        with open(os.path.join(self.dst.name, "rhs phile"), "w") as f:
            f.write("rhs contents\n")
        self._check_folders(cleaned=False, copied=False)
    def check(self):
        out = self.out.getvalue().split('\n')
        self.assertEqual(out[-1], "")
        del out[-1]
        if self.params.clean:
            self.assertEqual(out[0][:24], "lhs phile is new, remove")
            self.assertEqual(len(out), 1)
        else:
            self.assertEqual(out[0][:24], "lhs phile is new, create")
            self.assertEqual(out[1][:33], "rhs phile has disappeared, remove")
            self.assertEqual(len(out), 2)
        cleaned = self.affirmative() and self.params.clean
        copied = self.affirmative() and not self.params.clean
        self._check_folders(cleaned=cleaned, copied=copied)
    def _check_folders(self, cleaned, copied):
        for folder in self.src, self.dst:
            if folder is self.src and cleaned:
                self.assertEqual(os.listdir(self.src.name), [])
            elif folder is self.src or copied:
                self.assertEqual(os.listdir(folder.name), ["lhs phile"])
                with open(os.path.join(folder.name, "lhs phile"), "r") as f:
                    self.assertEqual(f.read(), "lhs contents\n")
            else:
                self.assertEqual(os.listdir(folder.name), ["rhs phile"])
                with open(os.path.join(folder.name, "rhs phile"), "r") as f:
                    self.assertEqual(f.read(), "rhs contents\n")

class MasterSessionTestCase_2_folders(MasterSessionTestCase):
    def setUp(self):
        super().setUp()
        for folder in self.src, self.dst:
            for subf in "pholder A", "pholder B":
                os.mkdir(os.path.join(folder.name, subf))
                for philename in "phile 1", "phile 2":
                    with open(os.path.join(folder.name, subf, philename), "w") as f:
                        if folder is self.src:
                            f.write("left contents in %s\n" % subf)
                        else:
                            assert folder is self.dst
                            f.write("right contents in %s\n" % subf)
        self._check_folders(cleaned=False, copied=False)
    def check(self):
        cleaned = self.affirmative() and self.params.clean
        copied = self.affirmative() and not self.params.clean
        self._check_folders(cleaned=cleaned, copied=copied)
    def _check_folders(self, cleaned, copied):
        for folder in self.src, self.dst:
            if folder is self.src and cleaned:
                self.assertEqual(os.listdir(folder.name), [])
            else:
                self.assertEqual(sorted(os.listdir(folder.name)), ["pholder A", "pholder B"])
                self.assertEqual(sorted(os.listdir(os.path.join(folder.name, "pholder A"))), ["phile 1", "phile 2"])
                self.assertEqual(sorted(os.listdir(os.path.join(folder.name, "pholder B"))), ["phile 1", "phile 2"])
                for philename in "phile 1", "phile 2":
                    if folder is self.src or copied:
                        with open(os.path.join(folder.name, "pholder A", philename), "r") as f:
                            self.assertEqual(f.read(), "left contents in pholder A\n")
                        with open(os.path.join(folder.name, "pholder B", philename), "r") as f:
                            self.assertEqual(f.read(), "left contents in pholder B\n")
                    elif folder is self.dst or not cleaned:
                        with open(os.path.join(folder.name, "pholder A", philename), "r") as f:
                            self.assertEqual(f.read(), "right contents in pholder A\n")
                        with open(os.path.join(folder.name, "pholder B", philename), "r") as f:
                            self.assertEqual(f.read(), "right contents in pholder B\n")

def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    params = Params()
    for params.clean in False, True:
        for params.follow_link in False, True:
            for params.ignore_time,params.trust_time in (False,False), (False,True), (True,False):
                for params.do_nothing,params.do_everything in (False,False), (False,True), (True,False):
                    # MasterSessionTestCase_empty
                    params.answers = []
                    suite.addTest(MasterSessionTestCase_empty(params))

                    if params.do_everything or params.do_nothing or not params.clean:
                        params.answers = []
                        suite.addTest(MasterSessionTestCase_2_files_identical(params))
                    else:
                        for answer in ['', 'n', 'N', 'Z', 'y', 'Y', 'A']:
                            params.answers = [answer]
                            suite.addTest(MasterSessionTestCase_2_files_identical(params))

                    # MasterSessionTestCase_2_files_same_name_size_time
                    if params.do_everything or params.do_nothing or (not params.clean and params.trust_time):
                        params.answers = []
                        suite.addTest(MasterSessionTestCase_2_files_same_name_size_time(params))
                    else:
                        for answer in ['', 'n', 'N', 'Z', 'y', 'Y', 'A']:
                            params.answers = [answer]
                            suite.addTest(MasterSessionTestCase_2_files_same_name_size_time(params))

                    # MasterSessionTestCase_2_files_same_name_size
                    if params.do_everything or params.do_nothing:
                        params.answers = []
                        suite.addTest(MasterSessionTestCase_2_files_same_name_size(params))
                    else:
                        for answer in ['', 'n', 'N', 'Z', 'y', 'Y', 'A']:
                            params.answers = [answer]
                            suite.addTest(MasterSessionTestCase_2_files_same_name_size(params))

                    # MasterSessionTestCase_2_files_same_name_contents
                    if params.do_everything or params.do_nothing or (not params.clean and params.ignore_time):
                        params.answers = []
                        suite.addTest(MasterSessionTestCase_2_files_same_name_contents(params))
                    else:
                        for answer in ['', 'n', 'N', 'Z', 'y', 'Y', 'A']:
                            params.answers = [answer]
                            suite.addTest(MasterSessionTestCase_2_files_same_name_contents(params))

                    # MasterSessionTestCase_2_different_files
                    if params.do_everything or params.do_nothing:
                        params.answers = []
                        suite.addTest(MasterSessionTestCase_2_different_files(params))
                    else:
                        for answer in ['', 'n', 'N', 'Z', 'y', 'Y', 'A']:
                            if params.clean:
                                params.answers = [answer]
                            else:
                                params.answers = [answer] * 2
                            suite.addTest(MasterSessionTestCase_2_different_files(params))

                    # MasterSessionTestCase_2_folders
                    # mostly checking the number of answers used.
                    if params.do_everything or params.do_nothing:
                        params.answers = []
                        suite.addTest(MasterSessionTestCase_2_folders(params))
                    else:
                        for params.answers in [['']*4, ['n']*4, ['N']*2, ['Z'], ['y']*4, ['Y']*2, ['A']]:
                            suite.addTest(MasterSessionTestCase_2_folders(params))
    return suite

del MasterSessionTestCase # hide from overzealous discovery (superseded by load_tests)

if __name__ == '__main__':
    unittest.main()
