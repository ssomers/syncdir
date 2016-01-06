import io
import syncdir
import unittest

class TracerTestCase(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        self.t = syncdir.Tracer(self.out)
    def tearDown(self):
        self.out.close()
    def runTest(self):
        self.assertEqual(self.out.getvalue(), "")

class TracerTestCase_report(TracerTestCase):
    def runTest(self):
        self.t.report("hi!")
        self.assertEqual(self.out.getvalue(), "hi!\n")

class TracerTestCase_trace_twice(TracerTestCase):
    def runTest(self):
        self.t.trace("hello!")
        self.assertEqual(self.out.getvalue(), "\rhello!")
        self.t.trace("bye!")
        self.assertEqual(self.out.getvalue(), "\rhello!\rbye!  \b\b")

class TracerTest_trace_many(TracerTestCase):
    def runTest(self):
        for l in range(82):
            with self.subTest(length=l):
                start = len(self.out.getvalue())
                self.t.trace("." * l)
                self.assertEqual(self.out.getvalue()[start:], "\r" + "." * min(l, 79))

class TracerTestCase_trace_and_report(TracerTestCase):
    def runTest(self):
        self.t.trace("hello!")
        self.t.report("bye!")
        self.assertEqual(self.out.getvalue(), "\rhello!\r      \rbye!\n")

if __name__ == '__main__':
    unittest.main()
