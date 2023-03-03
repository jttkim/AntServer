#!/usr/bin/env python3

import sys
import math
import random
import getopt

import AntNetwork
import AntNetwork.Client
import AntNetwork.Common
import SampleBotCommon


class AntObject:

    def __init__(self, antData):
        self.updatePosition(antData)

    def updatePosition(self, antData):
        self.x, self.y = SampleBotCommon.coords(antData)

    def isAt(self, other):
        return self.x == other.x and self.y == other.y

    def distance(self, other):
        return float(max(abs(self.x - other.x), abs(self.y - other.y)))

    def findClosest(self, antObjectList):
        # sys.stderr.write('findClosest: %d candidates\n' % len(antObjectList))
        # if len(antObjectList) < 20:
        #     for antObject in antObjectList:
        #         sys.stderr.write('  candidate: %s\n' % str(antObject))
        dMin = AntNetwork.Common.PLAYFIELDSIZE + 1
        closestObject = None
        for antObject in antObjectList:
            d = self.distance(antObject)
            # sys.stderr.write('findClosest: distance(%s -> %s) = %f\n' % (str(self), str(antObject), d))
            if dMin is None or d < dMin:
                # sys.stderr.write('findClosest: new min distance\n')
                dMin = d
                closestObject = antObject
        return closestObject
    
    def addToWorldDict(self, worldDict):
        worldDict[(self.x, self.y, )] = self


class Sugar(AntObject):

    def __init__(self, antData):
        super().__init__(antData)

    def __str__(self):
        return 'sugar at (%d, %d)' % (self.x, self.y)


class Toxin(AntObject):

    def __init__(self, antData):
        super().__init__(antData)

    def __str__(self):
        return 'toxin at (%d, %d)' % (self.x, self.y)


class HomePatch(AntObject):

    def __init__(self, team, coords):
        self.team = team
        self.x = coords[0]
        self.y = coords[1]

    def __str__(self):
        return 'home patch at (%d, %d)' % (self.x, self.y)


# Beware / Here Be Dragons:
# The classes in this module are designed to encapsulate information
# extracted from a turn, without tracking objects from one turn to the
# next.
# However, Ant objects are designed to keep track of history using a
# list of dictionaries containing their past states. This enables checking
# loss of energy, finding vectors of motion, and more.
# This requires to keep a collection, more specifically a dictionary containing
# teamIds as keys and dictionaries as values, where the nested dictionaries
# use antIds as keys and Ant objects as values. This enables lookup of the
# Ant instances using the teamId and antId information in the turn data, and
# using the updateState method of the Ant class, which appends a dictionary
# of attributes from the current state to the history before updating them.
class Ant(AntObject):

    def __init__(self, antData):
        self.teamId = None
        self.antId = None
        self.updateState(antData)
        self.stateHistory = []
        self.strategy = None

    def __str__(self):
        s = 's' if self.hasSugar else '-'
        t = 't' if self.hasSugar else '-'
        return 'ant %d:%d, (%d, %d), health %d, %s%s, strat=%s, age %d' % (self.teamId, self.antId, self.x, self.y, self.health, s, t, self.strategy, len(self.stateHistory))

    def getStateDict(self):
        return {k: self.__dict__[k] for k in ['teamId', 'antId', 'x', 'y', 'health', 'hasSugar', 'hasToxin']}

    def updateState(self, antData): 
        self.updatePosition(antData)
        if self.teamId is None and self.antId is None:
            self.teamId = SampleBotCommon.team(antData)
            self.antId = SampleBotCommon.ant_id(antData)
        elif self.teamId is not None and self.antId is not None:
            if self.teamId != SampleBotCommon.team(antData) or self.antId != SampleBotCommon.ant_id(antData):
                raise Exception('internal or server error: cannot update ant %d:%d from data on team %d:%d' % (self.teamId, self.antId, SampleBotCommon.team(antData), SampleBotCommon.ant_id(antData)))
            self.stateHistory.append(self.getStateDict())
        else:
            raise Exception('internal error: cannot update partially instantiated ant')
        self.health = SampleBotCommon.health(antData)
        self.hasSugar = SampleBotCommon.is_sugar(antData)
        self.hasToxin = SampleBotCommon.is_toxin(antData)

    def stepVectorTowards(self, other):
        # sys.stderr.write('stepVectorTowards: self = %s, other = %s\n' % (str(self), str(other)))
        dx = max(-1, min(other.x - self.x, 1))
        dy = max(-1, min(other.y - self.y, 1))
        return dx, dy

    def checkCollision(self, dx, dy, worldDict, avoidClassList):
        nx = self.x + dx
        ny = self.y + dy
        if (nx, ny, ) in worldDict:
            return worldDict[(nx, ny, )].__class__ in avoidClassList
        return False

    def actionStep(self, dx, dy):
        # sys.stderr.write('actionStep: dx: %s, type %s, dy: %s, type %s\n' % (str(dx), str(type(dx)), str(dy), str(type(dy))))
        if dy == -1:
            return dx + 2
        elif dy == 0:
            return dx + 5
        elif dy == 1:
            return dx + 8

    def actionStepTowards(self, other, worldDict=None, avoidClassList=None):
        alternativeStepDict = {
            (-1, -1): [(-1, 0), (0, -1), (-1, 1), (1, -1)],
            (0, -1): [(-1, -1), (1, -1), (-1, 0), (1, 0)],
            (1, -1): [(0, -1), (1, 0), (-1, -1), (1, 1)],
            (1, 0): [(1, -1), (1, 1), (0, -1), (0, 1)],
            (1, 1): [(1, 0), (0, 1), (1, -1), (-1, 1)],
            (0, 1): [(1, 1), (-1, 1), (1, 0), (-1, 0)],
            (-1, 1): [(-1, 0), (0, 1), (-1, -1), (1, 1)],
            (-1, 0): [(-1, -1), (-1, 1), (0, -1), (0, 1)]
            }
        dx, dy = self.stepVectorTowards(other)
        if (dx, dy) == (0, 0):
            return 5
        if worldDict is not None and avoidClassList is not None:
            for dx1, dy1 in [(dx, dy)] + alternativeStepDict[(dx, dy)]:
                if not self.checkCollision(dx1, dy1, worldDict, avoidClassList):
                    return self.actionStep(dx1, dy1)
        # action code 5 is for no move
        return 5


class Team:

    def __init__(self, teamData):
        self.teamId = None
        self.numPoints = teamData[0]
        self.numAnts = teamData[1]
        self.name = teamData[2].decode().split('\x00')[0]
        self.antDict = {}

    def __str__(self):
        return 'team %d: %s, %d points, %d ants' % (self.teamId, self.name, self.numPoints, self.numAnts)

    def printSummary(self, f=None):
        if f is None:
            f = sys.stderr
        f.write('%s\n' % str(self))
        for antId in range(AntNetwork.Common.ANTS):
            if antId in self.antDict:
                f.write('  %s\n' % str(self.antDict[antId]))
            else:
                f.write('  *** dead ***\n')


class AntTurnState:

    def __init__(self, turnData, allAntDict):
        self.teamId, teamDataList, antDataList = turnData
        homeCoords = SampleBotCommon.homebase_coords[self.teamId]
        # NOTE: afaiu teamdata always contain AntNetwork.Common.BASES teams
        self.teamList = [Team(teamData) for teamData in teamDataList]
        for teamId in range(len(self.teamList)):
            self.teamList[teamId].teamId = teamId
            self.teamList[teamId].homePatch = HomePatch(self.teamList[teamId], SampleBotCommon.homebase_coords[teamId])
        self.sugarList = []
        self.toxinList = []
        for antData in antDataList:
            if SampleBotCommon.is_ant(antData):
                teamId = SampleBotCommon.team(antData)
                antId = SampleBotCommon.ant_id(antData)
                if teamId in allAntDict and antId in allAntDict[teamId]:
                    ant = allAntDict[teamId][antId]
                    ant.updateState(antData)
                else:
                    ant = Ant(antData)
                    if teamId not in allAntDict:
                        allAntDict[teamId] = {}
                    if antId in allAntDict[teamId]:
                        raise Exception('internal error: inserting ant %d:%d but it is in dict already' % (ant.teamId, ant.antId))
                    allAntDict[teamId][antId] = ant
                # sys.stderr.write('adding ant %d to team %d\n' % (antId, teamId))
                self.teamList[teamId].antDict[antId] = ant
            elif SampleBotCommon.is_sugar(antData):
                self.sugarList.append(Sugar(antData))
            elif SampleBotCommon.is_toxin(antData):
                self.toxinList.append(Toxin(antData))
        self.allAntList = [ant for antTeamDict in allAntDict.values() for ant in antTeamDict.values()]
        self.homePatchList = [team.homePatch for team in self.teamList]
        self.worldDict = {}
        for antObject in self.sugarList + self.toxinList + self.allAntList + self.homePatchList:
            antObject.addToWorldDict(self.worldDict)

    def getTeam(self):
        return self.teamList[self.teamId]
    
    def getOtherTeamList(self):
        return [team for team in self.teamList if team.teamId != self.teamId]
    
    def getOtherAntList(self):
        return [ant for ant in self.allAntList if ant.teamId != self.teamId]

    def getHomePatch(self):
        return self.getTeam().homePatch

    def printSummary(self, f=None):
        if f is None:
            f = sys.stderr
        f.write('teamId: %d\n' % self.teamId)
        f.write('teamList: (%d teams)\n' % len(self.teamList))
        f.write('sugarList: (%d sugars)\n' % len(self.sugarList))
        f.write('toxinList: (%d toxins)\n' % len(self.toxinList))
        f.write('home: %s\n' % str(self.getHomePatch()))

    def printTeamSummary(self, f=None):
        self.getTeam().printSummary(f)


class Bot:
    
    def __init__(self, client):
        self.client = client
        self.allAntDict = {}

    def run(self, maxTurns=None):
        numTurns = 0
        try:
            while maxTurns is None or numTurns < maxTurns:
                self.turn()
                numTurns += 1
        except KeyboardInterrupt:
            sys.stderr.write('exited via keyboard interrupt\n')

    def save(self, fname):
        sys.stderr.write('saving %s -- not yet implemented\n' % fname)


class JtkBot(Bot):

    def __init__(self, client):
        super().__init__(client)

    def setStrategies(self, antTurnState):
        strategyDict = {
            0: 'hunt',
            1: 'hunt',
            2: 'hunt',
            3: 'gatherSugar',
            4: 'gatherToxin',
            5: 'hunt',
            6: 'hunt',
            7: 'hunt',
            8: 'gatherSugar',
            9: 'gatherToxin',
            10: 'hunt',
            11: 'hunt',
            12: 'hunt',
            13: 'gatherSugar',
            14: 'gatherSugar',
            15: 'gatherToxin'
            }
        antDict = antTurnState.getTeam().antDict
        for antId in antDict.keys():
            if antDict[antId].strategy is None:
                antDict[antId].strategy = strategyDict[antId]

    def actionGoHome(self, ant, antTurnState):
        if ant.hasToxin:
            return 0
        return ant.actionStepTowards(antTurnState.getHomePatch(), antTurnState.worldDict, [Ant, Toxin])

    def actionGatherSugar(self, ant, antTurnState):
        if ant.hasSugar:
            if ant.isAt(antTurnState.getHomePatch()):
                return 0
            return ant.actionStepTowards(antTurnState.getHomePatch(), antTurnState.worldDict, [Ant, Toxin])
        if len(antTurnState.sugarList) == 0:
            sys.stderr.write('actionGatherSugar: no sugar to gather, doing nothing then\n')
            return 5
        closestSugar = ant.findClosest(antTurnState.sugarList)
        # sys.stderr.write('%s: closest sugar is %s at %f\n' % (str(ant), str(closestSugar), ant.distance(closestSugar)))
        return ant.actionStepTowards(closestSugar, antTurnState.worldDict, [Ant, Toxin])

    def actionGatherToxin(self, ant, antTurnState):
        if ant.hasToxin:
            homePatchList = [team.homePatch for team in antTurnState.getOtherTeamList()]
            closestHomePatch = ant.findClosest(homePatchList)
            # sys.stderr.write('actionGatherToxin: moving to %s\n' % str(closestHomePatch))
            return ant.actionStepTowards(closestHomePatch, antTurnState.worldDict, [Ant, Toxin])
        if len(antTurnState.toxinList) == 0:
            sys.stderr.write('actionGatherToxin: no toxins, gathering sugar then\n')
            return self.actionGatherSugar(ant, antTurnState)
        closestToxin = ant.findClosest(antTurnState.toxinList)
        return ant.actionStepTowards(closestToxin, antTurnState.worldDict, [Ant, Sugar])

    def actionHunt(self, ant, antTurnState):
        otherAntList = antTurnState.getOtherAntList()
        if len(otherAntList) == 0:
            sys.stderr.write('actionHunt: no ants to hunt, gathering sugar then\n')
            return self.actionGatherSugar(ant, antTurnState)
        closestAnt = ant.findClosest(otherAntList)
        sys.stderr.write('actionHunt: %s hunting %s\n' % (str(ant), str(closestAnt)))
        return ant.actionStepTowards(closestAnt, antTurnState.worldDict, [Toxin, Sugar])

    def turn(self):
        antTurnState = AntTurnState(self.client.get_turn(), self.allAntDict)
        self.setStrategies(antTurnState)
        antTurnState.printSummary()
        antTurnState.printTeamSummary()
        ant = self.allAntDict[antTurnState.teamId][0]
        # for sugar in antTurnState.sugarList:
        #     sys.stderr.write('%s, %s: distance = %f\n' % (str(ant), str(sugar), ant.distance(sugar)))
        actionList = [0] * AntNetwork.Common.ANTS
        for ant in self.allAntDict[antTurnState.teamId].values():
            action = 5
            # go home, avoiding toxin, to heal when low on health
            if ant.health < 5:
                action = self.actionGoHome(ant, antTurnState)
            elif ant.strategy == 'hunt':
                action = self.actionHunt(ant, antTurnState)
            elif ant.strategy == 'gatherToxin':
                action = self.actionGatherToxin(ant, antTurnState)
            else:
                if ant.strategy != 'gatherSugar':
                    sys.stderr.write('unknown strategy %s, gathering sugar\n' % ant.strategy)
                # default is sugar gathering
                action = self.actionGatherSugar(ant, antTurnState)
            # sys.stderr.write('ant %d:%d: action code %d\n' % (ant.teamId, ant.antId, action))
            actionList[ant.antId] = action
        # sys.stderr.write('actionList: %s\n' % str(actionList))
        self.client.send_action(actionList)

        
class DoNothingBot(Bot):

    def __init__(self, client):
        super().__init__(client)
        
    def turn(self):
        antTurnState = AntTurnState(self.client.get_turn(), self.allAntDict)
        antTurnState.printSummary()
        antTurnState.printTeamSummary()
        self.client.send_action([5] * AntNetwork.Common.BASES)


def str2bot(botName):
    if botName == 'jtk':
        return JtkBot
    if botName == 'donothing':
        return DoNothingBot
    else:
        sys.stderr.write('unsupported bot name: %s\n' % botName)
        sys.exit(1)


def main():
    saveFname = None
    maxTurns = None
    botName = 'jtk'
    ipAddress = '127.0.0.1'
    teamName = None
    options, args = getopt.getopt(sys.argv[1:], 'm:b:i:t:h')
    for opt, par in options:
        if opt == '-h':
            print('options:')
            print('-h: print this help and exit')
            print('-m <maxTurns>')
            print('-i <ipAddress>')
            print('-t <teamName>')
            print('-b <bot> (see code for choices ;-)')
            sys.exit()
        elif opt == '-m':
            maxTurns = int(par)
        elif opt == '-i':
            ipAddress = par
        elif opt == '-t':
            teamName = par
        elif opt == '-b':
            botName = par
        else:
            raise(StandardError, 'unhandled option "%s"' % opt)
    if len(args) > 0:
        botName = args[0]
    if teamName is None:
        teamName = botName
    botClass = str2bot(botName)
    if len(args) > 1:
        saveFname = args[1]
    jtkBot = botClass(AntNetwork.Client.AntClient(ipAddress, 5000, teamName, True))
    jtkBot.run(maxTurns)


if __name__ == '__main__':
    main()
