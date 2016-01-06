#!/usr/bin/python -tu
import os
import sys
import difflib
import shutil
import stat
from datetime import datetime
from optparse import OptionParser

class Chooser:
    def ask(self, prompt):
        return input(prompt)

class Tracer:
    def __init__(self, out):
        self.tracing = 0
        self.out = out

    def report(self, str):
        if self.tracing:
            self.out.write('\r' + ''.join([' ' for i in range(self.tracing)]) + '\r')
            self.tracing = 0
        self.out.write(str + '\n')

    def trace(self, str):
        str = str[0:79]
        fill = self.tracing - len(str)
        self.out.write('\r' + str + ''.join([' ' for i in range(fill)]) + ''.join(['\b' for i in range(fill)]))
        self.tracing = len(str)

    def end(self, str = ''):
        if self.tracing:
            self.out.write(str + '\n')
            self.tracing = 0

    def leave(self):
        if self.tracing:
            self.out.write('\r' + ''.join([' ' for i in range(self.tracing)]) + '\r')
            self.tracing = 0

class Session:
    def __init__(self, mastersession, commonsubdir, initialdecisions):
        self.master = mastersession
        self.commonsubdir = commonsubdir
        self.__decisions = initialdecisions.copy()

    def getDecision(self, action):
        # returns True if permission will be granted
        # returns False if permission will be refused
        # returns None if question will be asked
        if self.master is not self:
            such_do = self.master.getDecision(action)
            if such_do is not None:
                return such_do
        return self.getOwnDecision(action)

    def getOwnDecision(self, action):
        try:
            return self.__decisions[action]
        except KeyError:
            return None

    def setDecision(self, action, granted):
        self.__decisions[action] = granted

    def canIdo(self, action, subject):
        # Recall or ask permission to do action, given (or not) explanation
        # arg 2: name of subject to treat
        # returns True if permission was granted

        tracer = self.master.tracer
        if action.isIgnore():
            tracer.trace("%s %s" % (subject, action.reason))
            return False
        such_do = self.getDecision(action)
        if such_do is not None:
            if such_do or self.master.do_nothing:
                tracer.report("%s %s, %s" % (subject, action.reason, action.treatment))
            return such_do
        while True:
            choice = "yes no"
            if self.master is not self:
                choice += " YesInDir NoInDir"
            choice += " AllYes ZeroYes Quit"
            tracer.leave()
            yn = self.master.chooser.ask("%s %s, %s? [%s] n\b" % (subject, action.reason, action.treatment, choice))
            if not yn:
                return False
            elif yn[0] == 'n':
                return False
            elif yn[0] == 'y':
                return True
            elif yn[0] == 'N':
                self.setDecision(action, False)
                return False
            elif yn[0] == 'Y':
                self.setDecision(action, True)
                return True
            elif yn[0] == 'Z':
                self.master.setDecision(action, False)
                return False
            elif yn[0] == 'A':
                self.master.setDecision(action, True)
                return True
            elif yn[0] == 'Q':
                sys.exit(1)
            else:
                tracer.report('Pardon?')

    def run(self):
        if self.commonsubdir:
            subdirA = os.path.join(self.master.dirA, self.commonsubdir)
            subdirB = os.path.join(self.master.dirB, self.commonsubdir)
        else:
            subdirA = self.master.dirA
            subdirB = self.master.dirB

        if not self.master.actionNewDir.isIgnore() and os.path.isdir(subdirA):
            basenamesA = os.listdir(subdirA)
        else:
            basenamesA = []
        if not self.master.actionOldDir.isIgnore() and os.path.isdir(subdirB):
            basenamesB = os.listdir(subdirB)
        else:
            basenamesB = []
        if basenamesA and basenamesB:
            basenames = list(set(basenamesA) | set(basenamesB))
        else:
            basenames = basenamesA or basenamesB
        basenames.sort()
        basename_aliases = set()
        for basename in basenames:
            if basename in basename_aliases:
                continue
            if self.commonsubdir:
                subject = os.path.join(self.commonsubdir, basename)
            else:
                subject = basename
            compair = ComPair(self, subject)
            compair.compare()
            for alt in (basename.upper(), basename.lower()):
                if alt != basename:
                    if compair.statA is not None:
                        try:
                            statA2 = os.lstat(os.path.join(subdirA, alt))
                        except EnvironmentError:
                            pass
                        else:
                            if os.path.samestat(compair.statA, statA2):
                                basename_aliases.add(alt)
                    if compair.statB is not None:
                        try:
                            statB2 = os.lstat(os.path.join(subdirB, alt))
                        except EnvironmentError:
                            pass
                        else:
                            if os.path.samestat(compair.statB, statB2):
                                basename_aliases.add(alt)

    def descend(self, subdir):
        Session(mastersession=self.master, commonsubdir=subdir, initialdecisions=self.__decisions).run()

class MasterSession(Session):
    def __init__(self, dirA, dirB, out, chooser, commonsubdir=None, clean=False, follow_link=False, do_everything=False, do_nothing=False, ignore_time=False, trust_time=False):
        assert not(do_everything and do_nothing)
        assert not(ignore_time and trust_time)
        Session.__init__(self, mastersession=self, commonsubdir=commonsubdir, initialdecisions={})
        self.dirA = dirA
        self.dirB = dirB
        self.follow_link = follow_link
        self.ignore_time = ignore_time
        self.trust_time = trust_time
        self.tracer = Tracer(out)
        self.chooser = chooser
        self.clean = clean
        if ignore_time:
            self.actionChangedTimestamp = Action("has different time")
        if not clean:
            self.actionNewDir = CreateTgtDir("is new", "create")
            self.actionOldDir = RemoveTgtDir("has disappeared", "descend & remove")
            self.actionNewFile = CopyFile("is new", "create")
            self.actionNewLink = CopyLink("is new", "link")
            self.actionOldFile = RemoveTgtFile("has disappeared", "remove")
            self.actionDuplicateFile = Action("has not changed")
            if not ignore_time:
                self.actionChangedTimestamp = CopyTimestamp("has different time", "touch")
            self.actionChangedFileUnknown = CopyFile("has changed somehow", "overwrite")
            self.actionChangedFileKnown = CopyFile("has changed as shown", "overwrite")
            self.actionChangedLink = CopyLink("has changed as shown", "relink")
        else:
            self.actionNewDir = RemoveSrcDir("is new", "descend")
            self.actionOldDir = Action("has disappeared")
            self.actionNewFile = RemoveSrcFile("is new", "remove")
            self.actionNewLink = RemoveSrcFile("is new", "remove")
            self.actionOldFile = Action("has disappeared")
            self.actionDuplicateFile = RemoveSrcFile("has not changed", "remove")
            if not ignore_time:
                self.actionChangedTimestamp = RemoveSrcFile("has different time", "remove")
            self.actionChangedFileUnknown = RemoveSrcFile("has changed somehow", "remove")
            self.actionChangedFileKnown = RemoveSrcFile("has changed as shown", "remove")
            self.actionChangedLink = RemoveSrcFile("has changed as shown", "remove")

        if do_everything or do_nothing:
            self.setDecision(self.actionNewDir, do_everything)
            self.setDecision(self.actionOldDir, do_everything)
            self.setDecision(self.actionNewFile, do_everything)
            self.setDecision(self.actionNewLink, do_everything)
            self.setDecision(self.actionOldFile, do_everything)
            self.setDecision(self.actionDuplicateFile, do_everything)
            self.setDecision(self.actionChangedTimestamp, do_everything)
            self.setDecision(self.actionChangedFileUnknown, do_everything)
            self.setDecision(self.actionChangedFileKnown, do_everything)
            self.setDecision(self.actionChangedLink, do_everything)
        self.do_nothing = do_nothing

    def TreatedCommonDir(self, compair):
        if self.clean:
            try:
                os.rmdir(compair.getPathA())
            except:
                pass

class ComPair:
    def __init__(self, session, subject):
        self.session = session
        self.subject = subject
        self.setStatA()
        self.setStatB()

    def getPathA(self):
        return os.path.join(self.session.master.dirA, self.subject)

    def getPathB(self):
        return os.path.join(self.session.master.dirB, self.subject)

    def setStatA(self):
        try:
            if self.session.master.follow_link:
                self.statA = os.stat(self.getPathA())
            else:
                self.statA = os.lstat(self.getPathA())
        except EnvironmentError:
            self.statA = None

    def setStatB(self):
        try:
            if self.session.master.follow_link:
                self.statB = os.lstat(self.getPathB())
            else:
                self.statB = os.lstat(self.getPathB())
        except EnvironmentError:
            self.statB = None

    def descendSubdir(self):
        self.session.descend(self.subject)

    def compare(self):
        master = self.session.master
        tracer = master.tracer
        if self.statA is None and self.statB is None:
            pass # suddenly removed
        elif self.statA is None:
            mode2 = self.statB[stat.ST_MODE]
            if stat.S_ISDIR(mode2):
                if master.actionOldFile.isIgnore() or self.session.getDecision(master.actionOldFile) is not False:
                    master.actionOldDir.performIfCan(self)
            else:
                master.actionOldFile.performIfCan(self)
        elif self.statB is None:
            mode1 = self.statA[stat.ST_MODE]
            if stat.S_ISDIR(mode1):
                master.actionNewDir.performIfCan(self)
            elif stat.S_ISREG(mode1):
                master.actionNewFile.performIfCan(self)
            elif stat.S_ISLNK(mode1):
                master.actionNewLink.performIfCan(self)
            else:
                tracer.report(self.subject + " skipped - huh???")
        else:
            mode1 = self.statA[stat.ST_MODE]
            mode2 = self.statB[stat.ST_MODE]
            if stat.S_ISDIR(mode1) and stat.S_ISDIR(mode2):
                self.descendSubdir()
                master.TreatedCommonDir(self)
            elif stat.S_ISREG(mode1) and stat.S_ISREG(mode2):
                action = self.cmpRegFiles()
                if action is not None:
                    if action in (master.actionChangedFileUnknown, master.actionChangedTimestamp): # and self.session.getDecision(action) is None:
                        tracer.report("%10i %s %s" % (self.statA[stat.ST_SIZE], datetime.fromtimestamp(self.statA[stat.ST_MTIME]).ctime(), master.dirA))
                        tracer.report("%10i %s %s" % (self.statB[stat.ST_SIZE], datetime.fromtimestamp(self.statB[stat.ST_MTIME]).ctime(), master.dirB))
                    action.performIfCan(self)
            elif stat.S_ISLNK(mode1) and stat.S_ISLNK(mode2):
                link1 = os.readlink(self.getPathA())
                link2 = os.readlink(self.getPathB())
                if link1 == link2:
                    master.actionDuplicateFile.performIfCan(self)
                else:
                    tracer.report(self.subject + " has changed as follows:\n- %s\n+ %s" % (link1, link2))
                    master.actionChangedLink.performIfCan(self)
            elif stat.S_ISLNK(mode1) and stat.S_ISREG(mode2):
                tracer.report(self.subject + " skipped - is link in source and file in target!")
            elif stat.S_ISLNK(mode1) and stat.S_ISDIR(mode2):
                tracer.report(self.subject + " skipped - is link in source and directory in target!")
            elif stat.S_ISREG(mode1) and stat.S_ISLNK(mode2):
                tracer.report(self.subject + " skipped - is file in source and link in target!")
            elif stat.S_ISDIR(mode1) and stat.S_ISLNK(mode2):
                tracer.report(self.subject + " skipped - is directory in source and link in target!")
            elif stat.S_ISREG(mode1) and stat.S_ISDIR(mode2):
                tracer.report(self.subject + " skipped - is file in source and directory in target!")
            elif stat.S_ISDIR(mode1) and stat.S_ISREG(mode2):
                tracer.report(self.subject + " skipped - is directory in source and file in target!")
            else:
                tracer.report(self.subject + " skipped - huh???")

    def cmpRegFiles(self):
        # returns relevant action
        master = self.session.master
        tracer = master.tracer
        size1 = self.statA[stat.ST_SIZE]
        size2 = self.statB[stat.ST_SIZE]
        maxsize = max(size1, size2)
        deltatime = self.statB[stat.ST_MTIME] - self.statA[stat.ST_MTIME]
        equaltime = master.ignore_time or abs(deltatime) in (0, 1, 3599, 3600, 3601, 7199, 7200, 7201)
        if maxsize == 0:
            if equaltime:
                return master.actionDuplicateFile
            else:
                return master.actionChangedTimestamp
        if size1 == size2 and master.trust_time and equaltime:
            return master.actionDuplicateFile
        #if self.session.getDecision(master.actionChangedFileUnknown) is not None:
            #return master.actionChangedFileUnknown

        BUFSIZE = 0x10000
        PROGRESSION = 10
        blocks = (maxsize + BUFSIZE - 1) // BUFSIZE
        if blocks > 1 and size1 != size2:
            return master.actionChangedFileUnknown
        if blocks > 1:
            tracer.trace(self.subject + ' ')
            with open(self.getPathA(), 'rb') as fileA:
                with open(self.getPathB(), 'rb') as fileB:
                    equal = True
                    progress = 0
                    for block in range(blocks):
                        update = False
                        while block * PROGRESSION >= progress * blocks:
                            progress += 1
                            update = True
                        if update:
                            sys.stdout.write(str(PROGRESSION - progress) + '\b')
                        b1 = fileA.read(BUFSIZE)
                        b2 = fileB.read(BUFSIZE)
                        equal = b1 is not None and b2 is not None and b1 == b2
                        if not equal:
                            break
            if equal:
                if equaltime:
                    return master.actionDuplicateFile
                else:
                    return master.actionChangedTimestamp
            else:
                tracer.report("different but won't detail because files are too big")
                return master.actionChangedFileUnknown
        else:
            try:
                fileA = open(self.getPathA())
                textA = fileA.readlines()
                fileA.close()
            except EnvironmentError:
                e = sys.exc_info()[1]
                tracer.report(e.strerror)
                return None
            try:
                fileB = open(self.getPathB())
                textB = fileB.readlines()
                fileB.close()
            except EnvironmentError:
                e = sys.exc_info()[1]
                tracer.report(e.strerror)
                return None
            if textA == textB:
                if equaltime:
                    return master.actionDuplicateFile
                else:
                    return master.actionChangedTimestamp

            binaryA = is_binary(textA)
            binaryB = is_binary(textB)
            if binaryA and binaryB:
                tracer.report(self.subject + " different but won't detail because both versions are binary")
                return master.actionChangedFileUnknown
            if binaryA:
                tracer.report(self.subject + " different but won't detail because source version is binary")
                return master.actionChangedFileUnknown
            if binaryB:
                tracer.report(self.subject + " different but won't detail because target version is binary")
                return master.actionChangedFileUnknown

            tracer.trace(self.subject + ' ')  # comparison might take a while, so give a clue
            difflines = [line for line in difflib.ndiff(textA, textB)]
            #if len(difflines) == 0:
                #print '\r',
                #return master.actionChangedFileWSonly
            #else:
            # TTYrows=$(stty -a | sed -n 's/^.*rows[ =]*\([0-9]*\).*$/\1/p')
            tracer.end(' - difference:\n' + ''.join(difflines))
            return master.actionChangedFileKnown


class Action:
    def __init__(self, reason, treatment=None):
        self.reason = reason
        self.treatment = treatment

    def isIgnore(self):
        return self.treatment is None

    def performIfCan(self, compair):
        return compair.session.canIdo(self, compair.subject) and self.perform(compair)

    def perform(self, compair):
        return True

class CreateTgtDir(Action):
    def perform(self, compair):
        os.mkdir(compair.getPathB())
        compair.setStatB()
        compair.descendSubdir()
        return True

class RemoveTgtDir(Action):
    def perform(self, compair):
        compair.descendSubdir()
        try:
            os.rmdir(compair.getPathB())
        except EnvironmentError:
            pass
        compair.setStatB()
        return True

class CopyTimestamp(Action):
    def perform(self, compair):
        os.utime(compair.getPathB(), (compair.statA[stat.ST_ATIME], compair.statA[stat.ST_MTIME]))
        return True

class CopyFile(Action):
    def perform(self, compair):
        shutil.copyfile(compair.getPathA(), compair.getPathB())
        os.utime(compair.getPathB(), (compair.statA[stat.ST_ATIME], compair.statA[stat.ST_MTIME]))
        compair.setStatB()
        return True

class CopyLink(Action):
    def perform(self, compair):
        link = os.readlink(compair.getPathA())
        try:
            os.unlink(compair.getPathB())
        except EnvironmentError:
            pass
        os.symlink(link, compair.getPathB())
        compair.setStatB()
        return True

class RemoveTgtFile(Action):
    def perform(self, compair):
        os.unlink(compair.getPathB())
        compair.setStatB()
        return True

class RemoveSrcFile(Action):
    def perform(self, compair):
        os.unlink(compair.getPathA())
        return True

class RemoveSrcDir(Action):
    def perform(self, compair):
        try:
            compair.descendSubdir()
            os.rmdir(compair.getPathA())
        except:
            pass

def is_binary(lines):
    for line in lines:
        for char in line:
            if ord(char) > 126 or ord(char) < 32 and char not in '\t\n\f\r':
                return True
    return False

if __name__ == '__main__':
    parser = OptionParser(usage="%prog [-L] [-c] [-r] [ -s | -i ] [ -y | -n ] source-directory destination-directory [-r] [ common-subdirectory ]")
    parser.add_option("-c", action="store_true", dest="clean", help="clean source instead")
    parser.add_option("-r", action="store_true", dest="reverse", help="reverse source and destination")
    parser.add_option("-s", action="store_true", dest="strict", help="compare contents even if timestamp and size match")
    parser.add_option("-i", action="store_true", dest="ignore_time", help="ignore time difference - consider equal if only size matches")
    parser.add_option("-L", action="store_true", dest="follow_link", help="follow symbolic links - otherwise treat link as files")
    parser.add_option("-y", action="store_true", dest="do_everything", help="always anwer yes")
    parser.add_option("-n", action="store_true", dest="do_nothing", help="always answer no")
    options, args = parser.parse_args()
    if options.do_everything and options.do_nothing:
        parser.error("Can't have both options")
        sys.exit(2)
    if options.strict and options.ignore_time:
        parser.error("Can't have both options")
        sys.exit(2)
    if len(args) not in (2, 3) or not os.path.isdir(args[0]) or not os.path.isdir(args[1]):
        parser.error("2 paths to directories needed")
        sys.exit(2)

    #------------------------------------#
    # application specific customization #
    #------------------------------------#
    dirA,dirB = args[0:2]
    if options.reverse:
        dirA,dirB = dirB,dirA
    master = MasterSession(dirA, dirB, commonsubdir=len(args) > 2 and args[2], clean=options.clean, follow_link=options.follow_link, do_everything=options.do_everything, do_nothing=options.do_nothing, ignore_time=options.ignore_time, trust_time=not options.strict, chooser=Chooser(), out=sys.stdout)

    try:
        master.run()
    except KeyboardInterrupt:
        master.tracer.report('cancelled')
    else:
        master.tracer.leave()
