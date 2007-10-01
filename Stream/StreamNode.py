from __future__ import division
import math, bisect
from warnings import warn
from ..Dieties import Chronos
from ..Dieties import IniParams
from StreamChannel import StreamChannel
from ..Utils.Logger import Logger
from ..Utils.easygui import indexbox, msgbox
Outfile = open("E:\evans.out","w")

class StreamNode(StreamChannel):
    """Definition of an individual stream segment"""
    def __init__(self, **kwargs):
        StreamChannel.__init__(self)
        # Define members in __slots__ to ensure that later member names cannot be added accidentally
        s = ["Latitude", "Longitude", "Elevation", # Geographic params
             "FLIR_Temp", "FLIR_Time", # FLIR data
             "T_sed", "T_in", "T_tribs", # Temperature attrs
             "VHeight", "VDensity", #Vegetation params
             "Wind", "Humidity", "T_air","Cloud", # Continuous data
             "Zone", "T_bc", # Initialization parameters, Zonator and boundary conditions
             "Delta_T", # Current temperature calculated from only local fluxes
             "T", "T_prev", # Current and previous stream temperature
             "Flux", # Dictionary to hold heat flux values
             "TopoFactor", # was Topo_W+Topo_S+Topo_E/(90*3) in original code. From Above stream surface solar flux calculations
             "ShaderList", # List of angles and attributes to determine sun shading.
             "F_DailySum", # Specific sums of solar fluxes
             "F_Solar", # List of important solar fluxes
             "Q_mb"]
        # Set all the attributes to bare lists, or set from the constructor
        for attr in s:
            x = kwargs[attr] if attr in kwargs.keys() else None
            setattr(self, attr, x)
        self.T = 0.0
        self.slots += s
        for attr in ["Wind", "Humidity", "T_air","Cloud", "T_tribs", "Q_tribs"]:
            setattr(self, attr, {})
        # Create an internal dictionary that we can pass to the C module, this contains self.slots attributes
        # and other things the C module needs
        for attr in ["F_Conduction","F_Convection","F_Longwave","F_Evaporation"]:
            setattr(self, attr, 0)
        self.F_Solar = [0]*8
        self.S1 = 0
        self.Log = Logger
        self.ShaderList = ()
    def __eq__(self, other):
        cmp = other.km if isinstance(other, StreamNode) else other
        return self.km == cmp
    def __ne__(self, other):
        cmp = other.km if isinstance(other, StreamNode) else other
        return self.km != cmp
    def __gt__(self, other):
        cmp = other.km if isinstance(other, StreamNode) else other
        return self.km > cmp
    def __lt__(self, other):
        cmp = other.km if isinstance(other, StreamNode) else other
        return self.km < cmp
    def __ge__(self, other):
        cmp = other.km if isinstance(other, StreamNode) else other
        return self.km >= cmp
    def __le__(self, other):
        cmp = other.km if isinstance(other, StreamNode) else other
        return self.km <= cmp
    def GetZones(self):
        return self.Zone
    def GetAttributes(self, zone=False):
        """Return a dictionary of all class attribute names and values

        This class returns a dictionary with keys that are the attribute name
        and values that are the current value for that attribute. All attributes
        in __slots__ and in self.slots (which hold the values for the StreamChannel)
        are included, including an optional breakdown of the values in the Zonator instance.

        If the argument zone is boolean True, then the values of the Zonator instance
        are given as well. The values in the Zonator are given differently named keys,
        in the form of X_Y_ATTR where X is the cardinal direction, clockwise from 0=NE to
        6=NW; Y is the zone number (0-4) and ATTR is the attribute name
        (e.g. VDensity). This dictionary can then be iterated over in a single
        call for printing. Internal dictionaries and lists are returned as objects
        and should be dealt with as such. (e.g. boundary conditions and such should
        be iterated over externally).
        """
        # Make a dictionary to return
        attrDict = {}
        ignoreList = ["Zone", "Chronos", "Helios", "IniParams", "Log"]
        # First we get all the attributes of __slots__
        for k in self.slots:
            if k in ignoreList: continue # Ignore the Zonator, clock, etc.
            try:
                attrDict[k] = getattr(self, k)
            except AttributeError:
                attrDict[k] = None
        if zone:
            for k, v in self.GetZoneAttributes().iteritems():
                attrDict[k] = v
        return attrDict
    def GetZoneAttributes(self):
        """Return a dictionary of key/value pairs for the internal Zonator instance.

        See GetAttributes() for details of the key format"""
        attrDict = {}
        # Expand the Zonator portion into the dictionary
        for i, j, zone in self.Zone:
            for attr in zone.__slots__:
                k = "%i_%i_%s" %(i, j, attr)
                attrDict[k] = getattr(zone, attr)
        return attrDict

    def CalcHydraulics(self, time, hour):
        self.Q_mass = 0
        try:
            self.CalculateDischarge(time, hour)
        except HeatSourceError, (stderr):
            msg = "At %s and time %s\n"%(self,time.isoformat(" ") )
            if isinstance(stderr,tuple):
                msg += """%s\n\tVariables causing this affliction:
    dt: %4.0f
    dx: %4.0f
    K: %4.4f
    X: %3.4f
    c_k: %3.4f""" % stderr
            else: msg += stderr

            msg += "\nThe model run has been halted. You may ignore any further error messages."
            msgbox(msg)
            raise SystemExit
        self.Q_mb += self.Q_mass # Add mass balance from the stream node

    def Initialize(self):
        """Methods necessary to set initial conditions of the node"""
        # This was emptied, but kept in case we want unanticipated initialization later.
        # ...
        # (Say "unanticipated initialization" 3 times, fast.)
        # ...
        pass

    def CalcHeat_Opt(self, hour, min, sec, bc_hour,JD,JDC,offset):
        """Inlined version of CalcHeat optimized for non-boundary nodes (removes a bunch of if/else statements)"""
        # Reset temperatures
        self.T_prev = self.T
        self.T = None
        # Calculate solar position (C module)
        Altitude, Zenith, Daytime, dir = self.head.SolarPos
        # Set some local variables if they're used more than once
        Elev = self.Elevation
        VTS = self.ViewToSky
        emerg = IniParams["emergent"]
        VHeight = self.VHeight
        cloud = self.Cloud[bc_hour]
        dt = self.dt
        dx = self.dx
        T_sed = self.T_sed
        T_prev = self.T_prev
        Q_hyp = self.Q_hyp
        ############################################
        ## Solar Flux Calculation, C-style
        # Testing method, these should return the same (to 1.0e-6 or so) result
#       self.F_Solar = self.Solar_THW(JD,time, hour, Altitude,Zenith,dir,IniParams["transsample"], Daytime)
        if Daytime:
            self.F_Solar = self.CalcSolarFlux(hour, JD, Altitude, Zenith, cloud, self.d_w,
                                              self.W_b, Elev, self.TopoFactor, VTS,
                                              IniParams["transsample"], self.phi, emerg,
                                              self.VDensity, VHeight, self.ShaderList[dir])
            self.F_DailySum[1] += self.F_Solar[1]
            self.F_DailySum[4] += self.F_Solar[4]
        else:
            self.F_Solar = [0]*8
        #Testing method, these should return the same (to 1.0e-6 or so) result
#        self.F_Conduction, self.T_sed, self.F_Longwave, self.F_LW_Atm, self.F_LW_Stream, \
#            self.F_LW_Veg, self.F_Evaporation, self.F_Convection, self.E = \
#            self.GroundFlux_THW(time)
        self.F_Conduction, self.T_sed, self.F_Longwave, self.F_LW_Atm, self.F_LW_Stream, \
                self.F_LW_Veg, self.F_Evaporation, self.F_Convection, self.E = \
                self.CalcGroundFluxes(cloud, self.Humidity[bc_hour], self.T_air[bc_hour], self.Wind[bc_hour], Elev,
                                    self.phi, VHeight, VTS, self.SedDepth, dx,
                                    dt, self.SedThermCond, self.SedThermDiff, self.T_alluv, self.P_w,
                                    self.W_w, emerg, IniParams["penman"], IniParams["wind_a"], IniParams["wind_b"],
                                    IniParams["calcevap"], T_prev, T_sed, Q_hyp, self.F_Solar[5], self.F_Solar[7])
        self.F_Total = self.F_Solar[6] + self.F_Conduction + self.F_Evaporation + self.F_Convection + self.F_Longwave
        self.Delta_T = self.F_Total * self.dt / ((self.A / self.W_w) * 4182 * 998.2) # Vars are Cp (J/kg *C) and P (kgS/m3)

        self.T, self.S1 = self.MacCormick(dt, dx, self.U, T_sed, T_prev, Q_hyp, self.Q_tribs[bc_hour], self.T_tribs[bc_hour],
                                          self.prev_km.Q_prev, self.Delta_T, self.Disp,
                                          False, 0.0, self.prev_km.T_prev, self.T_prev, self.next_km.T_prev, self.Q_in, self.T_in)
#            self.T, self.S1 = self.MacCormick_THW(bc_hour)

    def CalcHeat(self, hour, min, sec, bc_hour,JD,JDC,offset):
        # Reset temperatures
        self.T_prev = self.T
        self.T = None
        # Calculate solar position (C module)
        if self.prev_km: # Get position from headwater boundary node
            Altitude, Zenith, Daytime, dir = self.head.SolarPos
            self.CalcHeat = self.CalcHeat_Opt
        else: # Calculate position and store to a tuple
            Altitude, Zenith, Daytime, dir = self.CalcSolarPosition(self.Latitude, self.Longitude, hour, min, sec, offset, JDC)
            self.SolarPos = Altitude, Zenith, Daytime, dir
        # Set some local variables if they're used more than once
        Elev = self.Elevation
        VTS = self.ViewToSky
        emerg = IniParams["emergent"]
        VHeight = self.VHeight
        try:
            cloud = self.Cloud[bc_hour]
        except:
            print self
        dt = self.dt
        dx = self.dx
        T_sed = self.T_sed
        T_prev = self.T_prev
        Q_hyp = self.Q_hyp
        ############################################
        ## Solar Flux Calculation, C-style
        # Testing method, these should return the same (to 1.0e-6 or so) result
#       self.F_Solar = self.Solar_THW(JD,time, hour, Altitude,Zenith,dir,IniParams["transsample"], Daytime)
        if Daytime:
            self.F_Solar = self.CalcSolarFlux(hour, JD, Altitude, Zenith, cloud, self.d_w,
                                              self.W_b, Elev, self.TopoFactor, VTS,
                                              IniParams["transsample"], self.phi, emerg,
                                              self.VDensity, VHeight, self.ShaderList[dir])
            self.F_DailySum[1] += self.F_Solar[1]
            self.F_DailySum[4] += self.F_Solar[4]
        else:
            self.F_Solar = [0]*8
        #Testing method, these should return the same (to 1.0e-6 or so) result
#        self.F_Conduction, self.T_sed, self.F_Longwave, self.F_LW_Atm, self.F_LW_Stream, \
#            self.F_LW_Veg, self.F_Evaporation, self.F_Convection, self.E = \
#            self.GroundFlux_THW(time)
        self.F_Conduction, self.T_sed, self.F_Longwave, self.F_LW_Atm, self.F_LW_Stream, \
                self.F_LW_Veg, self.F_Evaporation, self.F_Convection, self.E = \
                self.CalcGroundFluxes(cloud, self.Humidity[bc_hour], self.T_air[bc_hour], self.Wind[bc_hour], Elev,
                                    self.phi, VHeight, VTS, self.SedDepth, dx,
                                    dt, self.SedThermCond, self.SedThermDiff, self.T_alluv, self.P_w,
                                    self.W_w, emerg, IniParams["penman"], IniParams["wind_a"], IniParams["wind_b"],
                                    IniParams["calcevap"], T_prev, T_sed, Q_hyp, self.F_Solar[5], self.F_Solar[7])
        self.F_Total = self.F_Solar[6] + self.F_Conduction + self.F_Evaporation + self.F_Convection + self.F_Longwave
        self.Delta_T = self.F_Total * self.dt / ((self.A / self.W_w) * 4182 * 998.2) # Vars are Cp (J/kg *C) and P (kgS/m3)

        # If we're a boundary node, we don't calculate MacCormick1, so get out quickly
        if not self.prev_km:
            self.T = self.T_bc[bc_hour]
            self.T_prev = self.T_bc[bc_hour]
            return

        self.T, self.S1 = self.MacCormick(dt, dx, self.U, T_sed, T_prev, Q_hyp, self.Q_tribs[bc_hour], self.T_tribs[bc_hour],
                                          self.prev_km.Q_prev, self.Delta_T, self.Disp,
                                          False, 0.0, self.prev_km.T_prev, self.T_prev, self.next_km.T_prev, self.Q_in, self.T_in)
#            self.T, self.S1 = self.MacCormick_THW(bc_hour)

    def MacCormick2(self, hour):
        #===================================================
        #Set control temps
        if not self.prev_km:
            return
        #===================================================
        self.T, S = self.MacCormick(self.dt, self.dx, self.U, self.T_sed, self.T_prev, self.Q_hyp,
                                    self.Q_tribs[hour], self.T_tribs[hour], self.prev_km.Q, self.Delta_T, self.Disp,
                                    True, self.S1, self.prev_km.T, self.T, self.next_km.T, self.Q_in, self.T_in)
#        self.T = self.MacCormick2_THW(hour)

    def CalcDispersion(self):
        dx = self.dx
        dt = self.dt
        if not self.S:
            Shear_Velocity = self.U
        else:
            Shear_Velocity = math.sqrt(9.8 * self.d_w * self.S)
        self.Disp = 0.011 * (self.U ** 2) * (self.W_w ** 2) / (self.d_w * Shear_Velocity)
        if self.Disp * dt / (dx ** 2) > 0.5:
            self.Disp = (0.45 * (dx ** 2)) / dt

    def MacCormick_THW(self, hour):
        dt = self.dt
        dx = self.dx
        mix = 0
        SkipNode = False
        if self.prev_km:
            if not SkipNode:
                mix = self.MixItUp(hour,self.prev_km.Q_prev, self.prev_km.T_prev) if self.Q else 0
                T0 = self.prev_km.T_prev + mix
                T1 = self.T_prev
                T2 = self.next_km.T_prev if self.next_km else self.T_prev
                Dummy1 = -self.U * (T1 - T0) / dx
                self.CalcDispersion()
                Dummy2 = self.Disp * (T2 - 2 * T1 + T0) / (dx ** 2)
                S1 = Dummy1 + Dummy2 + self.Delta_T / dt
                T = T1 + S1 * dt
            else:
                T = self.T_prev #TODO: This is wrong, really should be self.T_prev_prev
        else:
            T = self.T_bc[hour]
            T_prev = self.T_bc[hour]
        return T, S1

    def MacCormick_BoundaryNode(self,args):
        if not args[12]: # We're running the first time if we have no S value.
            self.T = self.T_bc[hour]
            self.T_prev = self.T_bc[hour]
        else:
            pass

    def MacCormick2_THW(self,hour):
        SkipNode = False
        if self.prev_km:
            if not SkipNode:
                mix = self.MixItUp(hour, self.prev_km.Q, self.prev_km.T) if self.Q else 0
                T0 = self.prev_km.T + mix
                T1 = self.T
                T2 = self.next_km.T if self.next_km else self.T
                #======================================================
                #Final MacCormick Finite Difference Calc.
                #===================================================
                Dummy1 = -self.U * (T1 - T0) / self.dx
                Dummy2 = self.Disp * (T2 - 2 * T1 + T0) / (self.dx ** 2)
                S2 = Dummy1 + Dummy2 + self.Delta_T / self.dt
                T = self.T_prev + ((self.S1 + S2) / 2) * self.dt
            else:
                T = self.T_prev
        else: T = self.T_prev
        if T > 50 or T < 0:
            raise Exception("Unstable model")
        return T

    def MixItUp(self, hour, Q_up, T_up):
        Q_in = 0
        T_in = 0
        for i in xrange(len(self.Q_tribs[hour])):
            Q_in += self.Q_tribs[hour][i] if self.Q_tribs[hour][i] > 0 else 0
            T_in += self.T_tribs[hour][i] if self.Q_tribs[hour][i] > 0 else 0

        # Hyporheic flows if available
        Q_hyp = self.Q_hyp or 0
        # And accretionary flows
        Q_accr = self.Q_in or 0
        T_accr = self.T_in or 0
        #Calculate temperature change from mass transfer from point inflows
        T_mix = ((Q_in * T_in) + (T_up * Q_up)) / (Q_up + Q_in)
        #Calculate temperature change from mass transfer from hyporheic zone
        T_mix = ((self.T_sed * Q_hyp) + (T_mix * (Q_up + Q_in))) / (Q_hyp + Q_up + Q_in)
        #Calculate temperature change from accretion inflows
        T_mix = ((Q_accr * T_accr) + (T_mix * (Q_up + Q_in + Q_hyp))) / (Q_accr + Q_up + Q_in + Q_hyp)
#            T_mix = ((Q_accr * T_accr) + (T_mix * (Q_up + Q_in))) / (Q_accr + Q_up + Q_in)
        return T_mix - T_up

    def Solar_THW(self,JD,time,hour, Altitude,Zenith,Direction,SampleDist):
        """Old method, now pushed down to a C module. This is left for testing only"""
        F_Direct = [0]*8
        F_Diffuse = [0]*8
        F_Solar = [0]*8
        FullSunAngle,TopoShadeAngle,BankShadeAngle,RipExtinction,VegetationAngle = self.ShaderList[Direction]
        # Make all math functions local to save time by preventing failed searches of local, class and global namespaces
        pi,exp,log10,log,sqrt = math.pi,math.exp,math.log10,math.log,math.sqrt
        sin,cos,tan,atan,radians = math.sin,math.cos,math.tan,math.atan,math.radians
        #======================================================
        # 0 - Edge of atmosphere
        # TODO: Original VB code's JulianDay calculation:
        # JulianDay = -DateDiff("d", theTime, DateSerial(year(theTime), 1, 1))
        # THis calculation for Rad_Vec should be checked, with respect to the DST hour/24 part.
        Rad_Vec = 1 + 0.017 * cos((2 * pi / 365) * (186 - JD + hour / 24))
        Solar_Constant = 1367 #W/m2
        F_Direct[0] = (Solar_Constant / (Rad_Vec ** 2)) * sin(radians(Altitude)) #Global Direct Solar Radiation
        F_Diffuse[0] = 0
        ########################################################
        #======================================================
        # 1 - Above Topography
        Air_Mass = (35 / sqrt(1224 * sin(radians(Altitude)) + 1)) * \
            exp(-0.0001184 * self.Elevation)
        Trans_Air = 0.0685 * cos((2 * pi / 365) * (JD + 10)) + 0.8
        #Calculate Diffuse Fraction
        F_Direct[1] = F_Direct[0] * (Trans_Air ** Air_Mass) * (1 - 0.65 * self.Cloud[time] ** 2)
        if F_Direct[0] == 0:
            Clearness_Index = 1
        else:
            Clearness_Index = F_Direct[1] / F_Direct[0]

        Dummy = F_Direct[1]
        Diffuse_Fraction = (0.938 + 1.071 * Clearness_Index) - \
            (5.14 * (Clearness_Index ** 2)) + \
            (2.98 * (Clearness_Index ** 3)) - \
            (sin(2 * pi * (JD - 40) / 365)) * \
            (0.009 - 0.078 * Clearness_Index)
        F_Direct[1] = Dummy * (1 - Diffuse_Fraction)
        F_Diffuse[1] = Dummy * (Diffuse_Fraction) * (1 - 0.65 * self.Cloud[time] ** 2)

        ########################################################
        #======================================================
        #2 - Above Land Cover
        # Empty
        ########################################################
        #======================================================
        #3 - Above Stream Surface (Above Bank Shade)
        if Altitude <= TopoShadeAngle:    #>Topographic Shade IS Occurring<
            F_Direct[2] = 0
            F_Diffuse[2] = F_Diffuse[1] * self.TopoFactor
            F_Direct[3] = 0
            F_Diffuse[3] = F_Diffuse[2] * self.ViewToSky
        elif Altitude < FullSunAngle:  #Partial shade from veg
            F_Direct[2] = F_Direct[1]
            F_Diffuse[2] = F_Diffuse[1] * (1 - self.TopoFactor)
            Dummy1 = F_Direct[2]
            zone = 0
            for vegangle in VegetationAngle:  #Loop to find if shading is occuring from veg. in that zone
                if Altitude < vegangle:  #veg shading is occurring from this zone
                    Dummy1 *= (1-(1-exp(-1* RipExtinction[zone] * (SampleDist/cos(radians(Altitude))))))
                zone += 1
            F_Direct[3] = Dummy1
            F_Diffuse[3] = F_Diffuse[2] * self.ViewToSky
        else: # Full sun
            F_Direct[2] = F_Direct[1]
            F_Diffuse[2] = F_Diffuse[1] * (1 - self.TopoFactor)
            F_Direct[3] = F_Direct[2]
            F_Diffuse[3] = F_Diffuse[2] * self.ViewToSky
        #4 - Above Stream Surface (What a Solar Pathfinder measures)
        #Account for bank shade
        if Altitude > TopoShadeAngle and Altitude <= BankShadeAngle:  #Bank shade is occurring
            F_Direct[4] = 0
            F_Diffuse[4] = F_Diffuse[3]
        else:  #bank shade is not occurring
            F_Direct[4] = F_Direct[3]
            F_Diffuse[4] = F_Diffuse[3]

        #Account for emergent vegetation
        if IniParams["emergent"]:
            pathEmergent = self.VHeight / sin(radians(Altitude))
            if pathEmergent > self.W_b:
                pathEmergent = self.W_b
            if self.VDensity == 1:
                self.VDensity = 0.9999
                ripExtinctEmergent = 1
                shadeDensityEmergent = 1
            elif self.VDensity == 0:
                self.VDensity = 0.00001
                ripExtinctEmergent = 0
                shadeDensityEmergent = 0
            else:
                ripExtinctEmergent = -log(1 - self.VDensity) / 10
                shadeDensityEmergent = 1 - exp(-ripExtinctEmergent * pathEmergent)
            F_Direct[4] = F_Direct[4] * (1 - shadeDensityEmergent)
            if self.VHeight: # if there's no VHeight, we get ZeroDivisionError because we don't need this next step
                pathEmergent = self.VHeight
                ripExtinctEmergent = -log(1 - self.VDensity) / self.VHeight
                shadeDensityEmergent = 1 - exp(-ripExtinctEmergent * pathEmergent)
                F_Diffuse[4] = F_Diffuse[4] * (1 - shadeDensityEmergent)

        #:::::::::::::::::::::::::::::::::::::::::::::::::::::::::
        #5 - Entering Stream
        if Zenith > 80:
            Stream_Reflect = 0.0515 * (Zenith) - 3.636
        else:
            Stream_Reflect = 0.091 * (1 / cos(Zenith * pi / 180)) - 0.0386
        if abs(Stream_Reflect) > 1:
            Stream_Reflect = 0.0515 * (Zenith * pi / 180) - 3.636
        if abs(Stream_Reflect) > 1:
            Stream_Reflect = 0.091 * (1 / self.cos(Zenith * pi / 180)) - 0.0386
        F_Diffuse[5] = F_Diffuse[4] * 0.91
        F_Direct[5] = F_Direct[4] * (1 - Stream_Reflect)
        #:::::::::::::::::::::::::::::::::::::::::::::::::::::::::
        #6 - Received by Water Column
        #=========================================================
        #:::::::::::::::::::::::::::::::::::::::::::::::::::::::::
        #7 - Received by Bed
        Water_Path = self.d_w / cos(atan((sin(radians(Zenith)) / 1.3333) / sqrt(-(sin(radians(Zenith)) / 1.3333) * (sin(radians(Zenith)) / 1.3333) + 1)))         #Jerlov (1976)
        Trans_Stream = 0.415 - (0.194 * log10(Water_Path * 100))
        if Trans_Stream > 1:
            Trans_Stream = 1
        Dummy1 = F_Direct[5] * (1 - Trans_Stream)       #Direct Solar Radiation attenuated on way down
        Dummy2 = F_Direct[5] - Dummy1                   #Direct Solar Radiation Hitting Stream bed
        Bed_Reflect = exp(0.0214 * (Zenith * pi / 180) - 1.941)   #Reflection Coef. for Direct Solar
        BedRock = 1 - self.phi
        Dummy3 = Dummy2 * (1 - Bed_Reflect)                #Direct Solar Radiation Absorbed in Bed
        Dummy4 = 0.53 * BedRock * Dummy3                   #Direct Solar Radiation Immediately Returned to Water Column as Heat
        Dummy5 = Dummy2 * Bed_Reflect                      #Direct Solar Radiation Reflected off Bed
        Dummy6 = Dummy5 * (1 - Trans_Stream)               #Direct Solar Radiation attenuated on way up
        F_Direct[6] = Dummy1 + Dummy4 + Dummy6
        F_Direct[7] = Dummy3 - Dummy4
        Trans_Stream = 0.415 - (0.194 * log10(100 * self.d_w))
        if Trans_Stream > 1:
            Trans_Stream = 1
        Dummy1 = F_Diffuse[5] * (1 - Trans_Stream)      #Diffuse Solar Radiation attenuated on way down
        Dummy2 = F_Diffuse[5] - Dummy1                  #Diffuse Solar Radiation Hitting Stream bed
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        # TODO: The following ALWAYS becomes exp(-1.941)
        Bed_Reflect = exp(0.0214 * (0) - 1.941)               #Reflection Coef. for Diffuse Solar
        Dummy3 = Dummy2 * (1 - Bed_Reflect)                #Diffuse Solar Radiation Absorbed in Bed
        Dummy4 = 0.53 * BedRock * Dummy3                   #Diffuse Solar Radiation Immediately Returned to Water Column as Heat
        Dummy5 = Dummy2 * Bed_Reflect                      #Diffuse Solar Radiation Reflected off Bed
        Dummy6 = Dummy5 * (1 - Trans_Stream)               #Diffuse Solar Radiation attenuated on way up
        F_Diffuse[6] = Dummy1 + Dummy4 + Dummy6
        F_Diffuse[7] = Dummy3 - Dummy4
        #=========================================================
#        '   Flux_Solar(x) and Flux_Diffuse = Solar flux at various positions
#        '       0 - Edge of atmosphere
#        '       1 - Above Topography
#        '       2 - Above Land Cover
#        '       3 - Above Stream (After Land Cover Shade)
#        '       4 - Above Stream (What a Solar Pathfinder Measures)
#        '       5 - Entering Stream
#        '       6 - Received by Water Column
#        '       7 - Received by Bed
        F_Solar[0] = F_Diffuse[0] + F_Direct[0]
        F_Solar[1] = F_Diffuse[1] + F_Direct[1]
        F_Solar[2] = F_Diffuse[2] + F_Direct[2]
        F_Solar[3] = F_Diffuse[3] + F_Direct[3]
        F_Solar[4] = F_Diffuse[4] + F_Direct[4]
        F_Solar[5] = F_Diffuse[5] + F_Direct[5]
        F_Solar[6] = F_Diffuse[6] + F_Direct[6]
        F_Solar[7] = F_Diffuse[7] + F_Direct[7]
        return F_Solar
    def GroundFlux_THW(self, hour):

        #SedThermCond units of W/(m *C)
        #SedThermDiff units of cm^2/sec

        SedRhoCp = self.SedThermCond / (self.SedThermDiff / 10000)
        #NOTE: SedRhoCp is the product of sediment density and heat capacity
        #since thermal conductivity is defined as density * heat capacity * diffusivity,
        #therefore (density * heat capacity) = (conductivity / diffusivity)  units of (J / m3 / *C)

        #Water Variable
        rhow = 1000                             #density of water kg / m3
        H2O_HeatCapacity = 4187                 #J/(kg *C)

        #Conduction flux (positive is heat into stream)
        F_Cond = self.SedThermCond * (self.T_sed - self.T_prev) / (self.SedDepth / 2)             #units of (W / m2)
        #Calculate the conduction flux between deeper alluvium & substrate
        if IniParams["calcalluvium"]:
            Flux_Conduction_Alluvium = self.SedThermCond * (self.T_sed - self.T_alluv) / (self.SedDepth / 2)
        else:
            Flux_Conduction_Alluvium = 0

        #Hyporheic flux (negative is heat into sediment)
        F_hyp = self.Q_hyp * rhow * H2O_HeatCapacity * (self.T_sed - self.T_prev) / (self.W_w * self.dx)

        NetFlux_Sed = self.F_Solar[7] - F_Cond - Flux_Conduction_Alluvium - F_hyp
        DT_Sed = NetFlux_Sed * self.dt / (self.SedDepth * SedRhoCp)
        T_sed_new = self.T_sed + DT_Sed

        #=====================================================
        #Calculate Longwave FLUX
        #=====================================================
        #Atmospheric variables
        exp = math.exp
        Humidity = self.Humidity[hour]
        Air_T = self.T_air[hour]
        Pressure = 1013 - 0.1055 * self.Elevation #mbar
        Sat_Vapor = 6.1275 * exp(17.27 * Air_T / (237.3 + Air_T)) #mbar (Chapra p. 567)
        Air_Vapor = self.Humidity[hour] * Sat_Vapor
        Sigma = 5.67e-8 #Stefan-Boltzmann constant (W/m2 K4)
        Emissivity = 1.72 * (((Air_Vapor * 0.1) / (273.2 + Air_T)) ** (1 / 7)) * (1 + 0.22 * self.Cloud[hour] ** 2) #Dingman p 282
        #======================================================
        #Calcualte the atmospheric longwave flux
        F_LW_Atm = 0.96 * self.ViewToSky * Emissivity * Sigma * (Air_T + 273.2) ** 4
        #Calcualte the backradiation longwave flux
        F_LW_Stream = -0.96 * Sigma * (self.T_prev + 273.2) ** 4
        #Calcualte the vegetation longwave flux
        F_LW_Veg = 0.96 * (1 - self.ViewToSky) * 0.96 * Sigma * (Air_T + 273.2) ** 4
        #Calcualte the net longwave flux
        F_Longwave = F_LW_Atm + F_LW_Stream + F_LW_Veg

        #===================================================
        #Calculate Evaporation FLUX
        #===================================================
        #Atmospheric Variables
        log,exp = math.log,math.exp
        Wind = self.Wind[hour]
        Air_T = self.T_air[hour]
        Humidity = self.Humidity[hour]
        Pressure = 1013 - 0.1055 * self.Elevation #mbar
        Sat_Vapor = 6.1275 * exp(17.27 * self.T_prev / (237.3 + self.T_prev)) #mbar (Chapra p. 567)
        Air_Vapor = self.Humidity[hour] * Sat_Vapor
        #===================================================
        #Calculate the frictional reduction in wind velocity
        if IniParams["emergent"] and self.VHeight > 0:
            Zd = 0.7 * self.VHeight
            Zo = 0.1 * self.VHeight
            Zm = 2
            Friction_Velocity = Wind * 0.4 / log((Zm - Zd) / Zo) #Vertical Wind Decay Rate (Dingman p. 594)
        else:
            Zo = 0.00023 #Brustsaert (1982) p. 277 Dingman
            Zd = 0 #Brustsaert (1982) p. 277 Dingman
            Zm = 2
            Friction_Velocity = Wind
        #===================================================
        #Wind Function f(w)
        Wind_Function = float(IniParams["wind_a"]) + float(IniParams["wind_b"]) * Friction_Velocity #m/mbar/s
#        Wind_Function = 0.000000001505 + 0.0000000016 * Friction_Velocity #m/mbar/s

        #===================================================
        #Latent Heat of Vaporization
        LHV = 1000 * (2501.4 + (1.83 * self.T_prev)) #J/kg
        #===================================================
        #Use Jobson Wind Function
        if IniParams["penman"]:
            #Calculate Evaporation FLUX
            P = 998.2 # kg/m3
            Gamma = 1003.5 * Pressure / (LHV * 0.62198) #mb/*C  Cuenca p 141
            Delta = 6.1275 * exp(17.27 * Air_T / (237.3 + Air_T)) - 6.1275 * exp(17.27 * (Air_T - 1) / (237.3 + Air_T - 1))
            NetRadiation = self.F_Solar[5] + F_Longwave  #J/m2/s
            if NetRadiation < 0:
                NetRadiation = 0 #J/m2/s
            Ea = Wind_Function * (Sat_Vapor - Air_Vapor)  #m/s
            Evap_Rate = ((NetRadiation * Delta / (P * LHV)) + Ea * Gamma) / (Delta + Gamma)
            F_Evap = -Evap_Rate * LHV * P #W/m2
            #Calculate Convection FLUX
            Bowen = Gamma * (self.T_prev - Air_T) / (Sat_Vapor - Air_Vapor)
        else:
            #===================================================
            #Calculate Evaporation FLUX
            Evap_Rate = Wind_Function * (Sat_Vapor - Air_Vapor)  #m/s
            P = 998.2 # kg/m3
            F_Evap = -Evap_Rate * LHV * P #W/m2
            #Calculate Convection FLUX
            if (Sat_Vapor - Air_Vapor) <> 0:
                Bowen = 0.61 * (Pressure / 1000) * (self.T_prev - Air_T) / (Sat_Vapor - Air_Vapor)
            else:
                Bowen = 1
            F_Conv = F_Evap * Bowen
        F_Conv = F_Evap * Bowen
        E = Evap_Rate*self.W_w if IniParams["calcevap"] else 0
        return F_Cond, T_sed_new, F_Longwave, F_LW_Atm, F_LW_Stream, F_LW_Veg, F_Evap, F_Conv, E

def CalcSolarPosition_THW(lat, lon, hour, minute, second, offset, JDC):

    MeanObliquity = 23.0 + (26.0 + ((21.448 - JDC * (46.815 + JDC * (0.00059 - JDC * 0.001813))) / 60.0)) / 60.0
    Obliquity = MeanObliquity + 0.00256 * cos(toRadians*(125.04 - 1934.136 * JDC))
    Eccentricity = 0.016708634 - JDC * (0.000042037 + 0.0000001267 * JDC)
    GeoMeanLongSun = 280.46646 + JDC * (36000.76983 + 0.0003032 * JDC)

    while GeoMeanLongSun < 0:
        GeoMeanLongSun += 360
    while GeoMeanLongSun > 360:
        GeoMeanLongSun -= 360
    GeoMeanAnomalySun = 357.52911 + JDC * (35999.05029 - 0.0001537 * JDC)

    Dummy1 = toRadians*GeoMeanAnomalySun
    Dummy2 = sin(Dummy1)
    Dummy3 = sin(Dummy2 * 2)
    Dummy4 = sin(Dummy3 * 3)
    SunEqofCenter = Dummy2 * (1.914602 - JDC * (0.004817 + 0.000014 * JDC)) + Dummy3 * (0.019993 - 0.000101 * JDC) + Dummy4 * 0.000289
    SunApparentLong = (GeoMeanLongSun + SunEqofCenter) - 0.00569 - 0.00478 * sin(toRadians*((125.04 - 1934.136 * JDC)))

    Dummy1 = sin(toRadians*Obliquity) * sin(toRadians*SunApparentLong)
    Declination = toDegrees*(atan(Dummy1 / sqrt(-Dummy1 * Dummy1 + 1)))

    SunRadVector = (1.000001018 * (1 - pow(Eccentricity,2))) / (1 + Eccentricity * cos(toRadians*(GeoMeanAnomalySun + SunEqofCenter)))

    #======================================================
    #Equation of time (minutes)
    Dummy = pow((tan(Obliquity * pi / 360)),2)
    Dummy1 = sin(toRadians*(2 * GeoMeanLongSun))
    Dummy2 = sin(toRadians*(GeoMeanAnomalySun))
    Dummy3 = cos(toRadians*(2 * GeoMeanLongSun))
    Dummy4 = sin(toRadians*(4 * GeoMeanLongSun))
    Dummy5 = sin(toRadians*(2 * GeoMeanAnomalySun))
    Et = toDegrees*(4 * (Dummy * Dummy1 - 2 * Eccentricity * Dummy2 + 4 * Eccentricity * Dummy * Dummy2 * Dummy3 - 0.5 * pow(Dummy,2) * Dummy4 - 1.25 * pow(Eccentricity,2) * Dummy5))

    SolarTime = (hour*60.0) + minute + (second/60.0) + (Et - 4.0 * -lon + (offset*60.0))

    while SolarTime > 1440.0:
        SolarTime -= 1440.0
    HourAngle = SolarTime / 4.0 - 180.0
    if HourAngle < -180.0:
        HourAngle += 360.0

    Dummy = sin(toRadians*lat) * sin(toRadians*Declination) + cos(toRadians*lat) * cos(toRadians*Declination) * cos(toRadians*HourAngle)
    if Dummy > 1.0:
        Dummy = 1.0
    elif Dummy < -1.0:
        Dummy = -1.0

    Zenith = toDegrees*(acos(Dummy))
    Dummy = cos(toRadians*lat) * sin(toRadians*Zenith)
    if abs(Dummy) >= 0.000999:
        Azimuth = (sin(toRadians*lat) * cos(toRadians*Zenith) - sin(toRadians*Declination)) / Dummy
        if abs(Azimuth) > 1.0:
            if Azimuth < 0:
                Azimuth = -1.0
            else:
                Azimuth = 1.0

        Azimuth = 180 - toDegrees*(acos(Azimuth))
        if HourAngle > 0:
            Azimuth *= -1.0
    else:
        if lat > 0:
            Azimuth = 180.0
        else:
            Azimuth = 0.0
    if Azimuth < 0:
        Azimuth += 360.0

    AtmElevation = 90 - Zenith
    if AtmElevation > 85:
        RefractionCorrection = 0
    else:
        Dummy = tan(toRadians*(AtmElevation))
        if AtmElevation > 5:
            RefractionCorrection = 58.1 / Dummy - 0.07 / pow(Dummy,3) + 0.000086 / pow(Dummy,5)
        elif AtmElevation > -0.575:
            RefractionCorrection = 1735 + AtmElevation * (-518.2 + AtmElevation * (103.4 + AtmElevation * (-12.79 + AtmElevation * 0.711)))
        else:
            RefractionCorrection = -20.774 / Dummy
        RefractionCorrection = RefractionCorrection / 3600

    Zenith = Zenith - RefractionCorrection
    Altitude = 90 - Zenith
    Daytime = 0
    if Altitude > 0.0:
            Daytime = 1

    dir = bisect((0.0,67.5,112.5,157.5,202.5,247.5,292.5),Azimuth)-1

    return Altitude, Zenith, Daytime, dir
