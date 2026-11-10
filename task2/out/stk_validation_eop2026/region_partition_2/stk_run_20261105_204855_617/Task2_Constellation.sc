stk.v.11.0
WrittenBy    STK_v11.6.0
BEGIN Scenario
    Name		 Task2_Constellation

    BEGIN Epoch

        Epoch		 1 Jan 2027 00:00:00.000000000
        SmartEpoch		
        BEGIN EVENT
            Epoch		 1 Jan 2027 00:00:00.000000000
            EpochState		 Explicit
        END EVENT


    END Epoch

    BEGIN Interval

        Start		 1 Jan 2027 00:00:00.000000000
        Stop		 8 Jan 2027 00:00:00.000000000
        SmartInterval		
        BEGIN EVENTINTERVAL
            StartEvent		
            BEGIN EVENT
                Epoch		 1 Jan 2027 00:00:00.000000000
                EpochState		 Explicit
            END EVENT
            StopEvent		
            BEGIN EVENT
                Epoch		 8 Jan 2027 00:00:00.000000000
                EpochState		 Explicit
            END EVENT
            IntervalState		 StartStop
        END EVENTINTERVAL

        EpochUsesAnalStart		 No
        AnimStartUsesAnalStart		 Yes
        AnimStopUsesAnalStop		 No

    END Interval

    BEGIN EOPFile

        InheritEOPSource		 No
        EOPFilename		 EOP-20261105.txt

    END EOPFile

    BEGIN GlobalPrefs
        SatelliteNoOrbWarning		 No
        MissilePerigeeWarning		 No
        MissileStopTimeWarning		 No
        AircraftWGS84Warning		 Always
    END GlobalPrefs

    BEGIN CentralBody

        PrimaryBody		 Earth

    END CentralBody

    BEGIN CentralBodyTerrain

        BEGIN CentralBody
            Name		 Earth
            UseTerrainCache		 Yes
            TotalCacheSize		 402653184

            BEGIN StreamingTerrain
                UseCurrentStreamingTerrainServer		 Yes
                CurrentStreamingTerrainServerName		 http://twsusecovacc01.agi.com/stk-terrain
                StreamingTerrainTilesetName		 world
                StreamingTerrainServerName		 assets.agi.com/stk-terrain/
                StreamingTerrainAzimuthElevationMaskEnabled		 No
                StreamingTerrainObscurationEnabled		 No
                StreamingTerrainCoverageGridObscurationEnabled		 No
            END StreamingTerrain
        END CentralBody

    END CentralBodyTerrain

    BEGIN StarCollection

        Name		 Hipparcos 2 Mag 6

    END StarCollection

    BEGIN ScenarioLicenses
        Module		 AMMProv11.6
        Module		 AMMv11.6
        Module		 ASTGv11.6
        Module		 CATv11.6
        Module		 CHAINSv11.6
        Module		 CONv11.6
        Module		 COVv11.6
        Module		 CRMv11.6
        Module		 DISv11.6
        Module		 EOIRv11.6
        Module		 HRMv11.6
        Module		 MexServv11.6
        Module		 RT3Clientv11.6
        Module		 RdrAdvEnv11.6
        Module		 SEETv11.6
        Module		 STKCAP
        Module		 STKExpertv11.6
        Module		 STKIntegrationv11.6
        Module		 STKParallelComputingv11.6
        Module		 STKXv11.6
        Module		 STKv11.6
        Module		 TERNv11.6
        Module		 TIREMv11.6
        Module		 UPropv11.6
        Module		 Underseav11.6
    END ScenarioLicenses

    BEGIN Extensions

        BEGIN ClsApp
            RangeConstraint		 5000
            ApoPeriPad		 30000
            OrbitPathPad		 100000
            TimeDistPad		 30000
            OutOfDate		 2.592e+06
            MaxApoPeriStep		 900
            ApoPeriAngle		 0.785398
            UseApogeePerigeeFilter		 Yes
            UsePathFilter		 No
            UseTimeFilter		 No
            UseOutOfDate		 Yes
            CreateSats		 No
            MaxSatsToCreate		 500
            UseModelScale		 No
            ModelScale		 0
            UseCrossRefDb		 Yes
            CollisionDB		 stkAllTLE.tce
            CollisionCrossRefDB		 stkAllTLE.sd
            ShowLine		 Yes
            AnimHighlight		 Yes
            StaticHighlight		 Yes
            UseLaunchWindow		 No
            LaunchWindowUseEntireTraj		 Yes
            LaunchWindowTrajMETStart		 0
            LaunchWindowTrajMETStop		 900
            LaunchWindowStart		 0
            LaunchWindowStop		 0
            LaunchMETOffset		 0
            LaunchWindowUseSecEphem		 No 
            LaunchWindowUseScenFolderForSecEphem		 Yes
            LaunchWindowUsePrimEphem		 No 
            LaunchWindowUseScenFolderForPrimEphem		 Yes
            LaunchWindowIntervalPtr		
            BEGIN EVENTINTERVAL
                BEGIN Interval
                    Start		 5 Nov 2026 04:00:00.000000000
                    Stop		 6 Nov 2026 04:00:00.000000000
                END Interval
                IntervalState		 Explicit
            END EVENTINTERVAL

            LaunchWindowUsePrimMTO		 No 
            GroupLaunches		 No 
            LWTimeConvergence		 0.001
            LWRelValueConvergence		 1e-08
            LWTSRTimeConvergence		 0.0001
            LWTSRRelValueConvergence		 1e-10
            LaunchWindowStep		 300
            MaxTSRStep		  1.8000000000000000e+02
            MaxTSRRelMotion		  2.0000000000000000e+01
            UseLaunchArea		 No 
            LaunchAreaOrientation		 North
            LaunchAreaAzimuth		 0
            LaunchAreaXLimits		 -10000 10000
            LaunchAreaYLimits		 -10000 10000
            LaunchAreaNumXIntrPnts		 1
            LaunchAreaNumYIntrPnts		 1
            LaunchAreaAltReference		 Ellipsoid
            TargetSameStop		 No 
            SkipSurfaceMetric		 No 
            LWAreaTSRRelValueConvergence		 1e-10
            AreaLaunchWindowStep		 300
            AreaMaxTSRStep		  3.0000000000000000e+01
            AreaMaxTSRRelMotion		 1
            ShowLaunchArea		 No 
            ShowBlackoutTracks		 No 
            ShowClearedTracks		 No 
            UseObjectForClearedColor		 No 
            ShowTracksSegments		 Yes
            ShowMinRangeTracks		 Yes
            MinRangeTrackTimeStep		 0.5
            UsePrimStepForTracks		 Yes
            GfxTracksTimeStep		 30
            GfxAreaNumXIntrPnts		 1
            GfxAreaNumYIntrPnts		 1
            CreateLaunchMTO		 No 
            CovarianceSigmaScale		 3
            CovarianceMode		 None 
        END ClsApp

        BEGIN Units
            DistanceUnit		 Kilometers
            TimeUnit		 Seconds
            DateFormat		 GregorianUTC
            AngleUnit		 Degrees
            MassUnit		 Kilograms
            PowerUnit		 dBW
            FrequencyUnit		 Gigahertz
            SmallDistanceUnit		 Meters
            LatitudeUnit		 Degrees
            LongitudeUnit		 Degrees
            DurationUnit		 Hr:Min:Sec
            Temperature		 Kelvin
            SmallTimeUnit		 Seconds
            RatioUnit		 Decibel
            RcsUnit		 Decibel
            DopplerVelocityUnit		 MetersperSecond
            SARTimeResProdUnit		 Meter-Second
            ForceUnit		 Newtons
            PressureUnit		 Pascals
            SpecificImpulseUnit		 Seconds
            PRFUnit		 Kilohertz
            BandwidthUnit		 Megahertz
            SmallVelocityUnit		 CentimetersperSecond
            Percent		 Percentage
            AviatorDistanceUnit		 NauticalMiles
            AviatorTimeUnit		 Hours
            AviatorAltitudeUnit		 Feet
            AviatorFuelQuantityUnit		 Pounds
            AviatorRunwayLengthUnit		 Kilofeet
            AviatorBearingAngleUnit		 Degrees
            AviatorAngleOfAttackUnit		 Degrees
            AviatorAttitudeAngleUnit		 Degrees
            AviatorGUnit		 StandardSeaLevelG
            SolidAngle		 Steradians
            AviatorTSFCUnit		 TSFCLbmHrLbf
            AviatorPSFCUnit		 PSFCLbmHrHp
            AviatorForceUnit		 Pounds
            AviatorPowerUnit		 Horsepower
            SpectralBandwidthUnit		 Hertz
            AviatorAltTimeUnit		 Minutes
            AviatorSmallTimeUnit		 Seconds
            AviatorEnergyUnit		 kilowatt-hours
            BitsUnit		 MegaBits
            RadiationDose		 Rads
            MagneticFieldUnit		 nanoTesla
            RadiationShieldThickness		 Mils
            ParticleEnergy		 MeV
        END Units

        BEGIN ReportUnits
            DistanceUnit		 Kilometers
            TimeUnit		 Seconds
            DateFormat		 GregorianUTC
            AngleUnit		 Degrees
            MassUnit		 Kilograms
            PowerUnit		 dBW
            FrequencyUnit		 Gigahertz
            SmallDistanceUnit		 Meters
            LatitudeUnit		 Degrees
            LongitudeUnit		 Degrees
            DurationUnit		 Hr:Min:Sec
            Temperature		 Kelvin
            SmallTimeUnit		 Seconds
            RatioUnit		 Decibel
            RcsUnit		 Decibel
            DopplerVelocityUnit		 MetersperSecond
            SARTimeResProdUnit		 Meter-Second
            ForceUnit		 Newtons
            PressureUnit		 Pascals
            SpecificImpulseUnit		 Seconds
            PRFUnit		 Kilohertz
            BandwidthUnit		 Megahertz
            SmallVelocityUnit		 CentimetersperSecond
            Percent		 Percentage
            AviatorDistanceUnit		 NauticalMiles
            AviatorTimeUnit		 Hours
            AviatorAltitudeUnit		 Feet
            AviatorFuelQuantityUnit		 Pounds
            AviatorRunwayLengthUnit		 Kilofeet
            AviatorBearingAngleUnit		 Degrees
            AviatorAngleOfAttackUnit		 Degrees
            AviatorAttitudeAngleUnit		 Degrees
            AviatorGUnit		 StandardSeaLevelG
            SolidAngle		 Steradians
            AviatorTSFCUnit		 TSFCLbmHrLbf
            AviatorPSFCUnit		 PSFCLbmHrHp
            AviatorForceUnit		 Pounds
            AviatorPowerUnit		 Horsepower
            SpectralBandwidthUnit		 Hertz
            AviatorAltTimeUnit		 Minutes
            AviatorSmallTimeUnit		 Seconds
            AviatorEnergyUnit		 kilowatt-hours
            BitsUnit		 MegaBits
            RadiationDose		 Rads
            MagneticFieldUnit		 nanoTesla
            RadiationShieldThickness		 Mils
            ParticleEnergy		 MeV
        END ReportUnits

        BEGIN ConnectReportUnits
            DistanceUnit		 Kilometers
            TimeUnit		 Seconds
            DateFormat		 GregorianUTC
            AngleUnit		 Degrees
            MassUnit		 Kilograms
            PowerUnit		 dBW
            FrequencyUnit		 Gigahertz
            SmallDistanceUnit		 Meters
            LatitudeUnit		 Degrees
            LongitudeUnit		 Degrees
            DurationUnit		 Hr:Min:Sec
            Temperature		 Kelvin
            SmallTimeUnit		 Seconds
            RatioUnit		 Decibel
            RcsUnit		 Decibel
            DopplerVelocityUnit		 MetersperSecond
            SARTimeResProdUnit		 Meter-Second
            ForceUnit		 Newtons
            PressureUnit		 Pascals
            SpecificImpulseUnit		 Seconds
            PRFUnit		 Kilohertz
            BandwidthUnit		 Megahertz
            SmallVelocityUnit		 CentimetersperSecond
            Percent		 Percentage
            AviatorDistanceUnit		 NauticalMiles
            AviatorTimeUnit		 Hours
            AviatorAltitudeUnit		 Feet
            AviatorFuelQuantityUnit		 Pounds
            AviatorRunwayLengthUnit		 Kilofeet
            AviatorBearingAngleUnit		 Degrees
            AviatorAngleOfAttackUnit		 Degrees
            AviatorAttitudeAngleUnit		 Degrees
            AviatorGUnit		 StandardSeaLevelG
            SolidAngle		 Steradians
            AviatorTSFCUnit		 TSFCLbmHrLbf
            AviatorPSFCUnit		 PSFCLbmHrHp
            AviatorForceUnit		 Pounds
            AviatorPowerUnit		 Horsepower
            SpectralBandwidthUnit		 Hertz
            AviatorAltTimeUnit		 Minutes
            AviatorSmallTimeUnit		 Seconds
            AviatorEnergyUnit		 kilowatt-hours
            BitsUnit		 MegaBits
            RadiationDose		 Rads
            MagneticFieldUnit		 nanoTesla
            RadiationShieldThickness		 Mils
            ParticleEnergy		 MeV
        END ConnectReportUnits

        BEGIN ReportFavorites
        END ReportFavorites

        BEGIN ADFFileData
        END ADFFileData

        BEGIN GenDb

            BEGIN Database
                DbType		 Satellite
                DefDb		 stkAllTLE.sd
                UseMyDb		 Off
                MaxMatches		 2000
                Use4SOC		 On

                BEGIN FieldDefaults

                    BEGIN Field
                        Name		 "SSC Number"
                        Default		 "*"
                    END Field

                    BEGIN Field
                        Name		 "Common Name"
                        Default		 "*"
                    END Field

                END FieldDefaults

            END Database

            BEGIN Database
                DbType		 City
                DefDb		 stkCityDb.cd
                UseMyDb		 Off
                MaxMatches		 2000
                Use4SOC		 On

                BEGIN FieldDefaults

                    BEGIN Field
                        Name		 "City Name"
                        Default		 "*"
                    END Field

                END FieldDefaults

            END Database

            BEGIN Database
                DbType		 Facility
                DefDb		 stkFacility.fd
                UseMyDb		 Off
                MaxMatches		 2000
                Use4SOC		 On

                BEGIN FieldDefaults

                END FieldDefaults

            END Database
        END GenDb

        BEGIN SOCDb
            BEGIN Defaults
            END Defaults
        END SOCDb

        BEGIN Msgp4Ext
        END Msgp4Ext

        BEGIN FileLocations
        END FileLocations

        BEGIN Author
            Optimize		 No
            UseBasicGlobe		 No
            SaveEphemeris		 Yes
            SaveScenFolder		 No
            BEGIN ExternalFileTypes
                BEGIN Type
                    FileType		 Calculation Scalar
                    Include		 Yes
                END Type
                BEGIN Type
                    FileType		 EOP
                    Include		 Yes
                END Type
                BEGIN Type
                    FileType		 External Vector Data
                    Include		 Yes
                END Type
                BEGIN Type
                    FileType		 Object Break-up File
                    Include		 No
                END Type
                BEGIN Type
                    FileType		 Planetary Ephemeris
                    Include		 No
                END Type
                BEGIN Type
                    FileType		 Report Style Script
                    Include		 Yes
                END Type
                BEGIN Type
                    FileType		 Report/Graph Style
                    Include		 Yes
                END Type
                BEGIN Type
                    FileType		 Scalar Calculation File
                    Include		 Yes
                END Type
                BEGIN Type
                    FileType		 Terrain
                    Include		 Yes
                END Type
                BEGIN Type
                    FileType		 Volume Grid Intervals File
                    Include		 Yes
                END Type
                BEGIN Type
                    FileType		 Volumetric File
                    Include		 Yes
                END Type
            END ExternalFileTypes
            ReadOnly		 No
            ViewerPassword		 No
            STKPassword		 No
            ExcludeInstallFiles		 No
            BEGIN ExternalFileList
            END ExternalFileList
        END Author

        BEGIN ExportDataFile
            FileType		 Ephemeris
            IntervalType		 Ephemeris
            TimePeriodStart		 0
            TimePeriodStop		 0
            StepType		 Ephemeris
            StepSize		 60
            EphemType		 STK
            UseVehicleCentralBody		 Yes
            CentralBody		 Earth
            SatelliteID		 -200000
            CoordSys		 ICRF
            NonSatCoordSys		 Fixed
            InterpolateBoundaries		 Yes
            EphemFormat		 Current
            InterpType		 9
            InterpOrder		 5
            AttCoordSys		 Fixed
            Quaternions		 0
            ExportCovar		 Position
            AttitudeFormat		 Current
            TimePrecision		 6
            CCSDSDateFormat		 YMD
            CCSDSEphFormat		 SciNotation
            CCSDSTimeSystem		 UTC
            CCSDSRefFrame		 ICRF
            UseSatCenterAndFrame		 No
            IncludeCovariance		 No
            IncludeAcceleration		 No
            CCSDSFileFormat		 KVN
        END ExportDataFile

        BEGIN Desc
        END Desc

        BEGIN RfEnv
<?xml version = "1.0" standalone = "yes"?>
<VAR name = "STK_RF_Environment">
    <SCOPE Class = "RFEnvironment">
        <VAR name = "Version">
            <STRING>&quot;1.0.0 a&quot;</STRING>
        </VAR>
        <VAR name = "STKVersion">
            <INT>1160</INT>
        </VAR>
        <VAR name = "ComponentName">
            <STRING>&quot;STK_RF_Environment&quot;</STRING>
        </VAR>
        <VAR name = "Description">
            <STRING>&quot;STK RF Environment&quot;</STRING>
        </VAR>
        <VAR name = "Type">
            <STRING>&quot;STK RF Environment&quot;</STRING>
        </VAR>
        <VAR name = "UserComment">
            <STRING>&quot;STK RF Environment&quot;</STRING>
        </VAR>
        <VAR name = "ReadOnly">
            <BOOL>false</BOOL>
        </VAR>
        <VAR name = "Clonable">
            <BOOL>true</BOOL>
        </VAR>
        <VAR name = "Category">
            <STRING>&quot;&quot;</STRING>
        </VAR>
        <VAR name = "PropagationChannel">
            <VAR name = "RF_Propagation_Channel">
                <SCOPE Class = "PropagationChannel">
                    <VAR name = "Version">
                        <STRING>&quot;1.0.0 a&quot;</STRING>
                    </VAR>
                    <VAR name = "STKVersion">
                        <INT>1160</INT>
                    </VAR>
                    <VAR name = "ComponentName">
                        <STRING>&quot;RF_Propagation_Channel&quot;</STRING>
                    </VAR>
                    <VAR name = "Description">
                        <STRING>&quot;RF Propagation Channel&quot;</STRING>
                    </VAR>
                    <VAR name = "Type">
                        <STRING>&quot;RF Propagation Channel&quot;</STRING>
                    </VAR>
                    <VAR name = "UserComment">
                        <STRING>&quot;RF Propagation Channel&quot;</STRING>
                    </VAR>
                    <VAR name = "ReadOnly">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "Clonable">
                        <BOOL>true</BOOL>
                    </VAR>
                    <VAR name = "Category">
                        <STRING>&quot;&quot;</STRING>
                    </VAR>
                    <VAR name = "UseITU618Section2p5">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "UseCloudFogModel">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "CloudFogModel">
                        <VAR name = "ITU-R_P840-6">
                            <SCOPE Class = "CloudFogLossModel">
                                <VAR name = "Version">
                                    <STRING>&quot;1.0.0 a&quot;</STRING>
                                </VAR>
                                <VAR name = "STKVersion">
                                    <INT>1160</INT>
                                </VAR>
                                <VAR name = "ComponentName">
                                    <STRING>&quot;ITU-R_P840-6&quot;</STRING>
                                </VAR>
                                <VAR name = "Description">
                                    <STRING>&quot;ITU-R P840-6&quot;</STRING>
                                </VAR>
                                <VAR name = "Type">
                                    <STRING>&quot;ITU-R P840-6&quot;</STRING>
                                </VAR>
                                <VAR name = "UserComment">
                                    <STRING>&quot;ITU-R P840-6&quot;</STRING>
                                </VAR>
                                <VAR name = "ReadOnly">
                                    <BOOL>false</BOOL>
                                </VAR>
                                <VAR name = "Clonable">
                                    <BOOL>true</BOOL>
                                </VAR>
                                <VAR name = "Category">
                                    <STRING>&quot;&quot;</STRING>
                                </VAR>
                                <VAR name = "LiquidWaterDensityValueChoice">
                                    <STRING>&quot;Liquid Water Content Density Value&quot;</STRING>
                                </VAR>
                                <VAR name = "CloudCeiling">
                                    <QUANTITY Dimension = "DistanceUnit" Unit = "m">
                                        <REAL>3000</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "CloudLayerThickness">
                                    <QUANTITY Dimension = "DistanceUnit" Unit = "m">
                                        <REAL>500</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "CloudTemp">
                                    <QUANTITY Dimension = "Temperature" Unit = "K">
                                        <REAL>273.15</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "CloudLiqWaterDensity">
                                    <QUANTITY Dimension = "SmallDensity" Unit = "kg*m^-3">
                                        <REAL>0.0075</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "AnnualAveragePercentValue">
                                    <QUANTITY Dimension = "Percent" Unit = "unitValue">
                                        <REAL>0.01</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "MonthlyAveragePercentValue">
                                    <QUANTITY Dimension = "Percent" Unit = "unitValue">
                                        <REAL>0.01</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "LiqWaterAverageDataMonth">
                                    <INT>1</INT>
                                </VAR>
                            </SCOPE>
                        </VAR>
                    </VAR>
                    <VAR name = "UseTropoScintModel">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "TropoScintModel">
                        <VAR name = "ITU-R_P618-12">
                            <SCOPE Class = "TropoScintLossModel">
                                <VAR name = "Version">
                                    <STRING>&quot;1.0.0 a&quot;</STRING>
                                </VAR>
                                <VAR name = "STKVersion">
                                    <INT>1160</INT>
                                </VAR>
                                <VAR name = "ComponentName">
                                    <STRING>&quot;ITU-R_P618-12&quot;</STRING>
                                </VAR>
                                <VAR name = "Description">
                                    <STRING>&quot;ITU-R P618-12&quot;</STRING>
                                </VAR>
                                <VAR name = "Type">
                                    <STRING>&quot;ITU-R P618-12&quot;</STRING>
                                </VAR>
                                <VAR name = "UserComment">
                                    <STRING>&quot;ITU-R P618-12&quot;</STRING>
                                </VAR>
                                <VAR name = "ReadOnly">
                                    <BOOL>false</BOOL>
                                </VAR>
                                <VAR name = "Clonable">
                                    <BOOL>true</BOOL>
                                </VAR>
                                <VAR name = "Category">
                                    <STRING>&quot;&quot;</STRING>
                                </VAR>
                                <VAR name = "FadeDepthAverageTimeChoice">
                                    <STRING>&quot;Fade depth for the average year&quot;</STRING>
                                </VAR>
                                <VAR name = "ComputeDeepFade">
                                    <BOOL>false</BOOL>
                                </VAR>
                                <VAR name = "FadeOutage">
                                    <QUANTITY Dimension = "Percent" Unit = "unitValue">
                                        <REAL>0.001</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "PercentTimeRefracGrad">
                                    <QUANTITY Dimension = "Percent" Unit = "unitValue">
                                        <REAL>0.1</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "SurfaceTemperature">
                                    <QUANTITY Dimension = "Temperature" Unit = "K">
                                        <REAL>273.15</REAL>
                                    </QUANTITY>
                                </VAR>
                            </SCOPE>
                        </VAR>
                    </VAR>
                    <VAR name = "UseIonoFadingModel">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "IonoFadingModel">
                        <VAR name = "ITU-R_P531-13">
                            <SCOPE Class = "IonoFadingLossModel">
                                <VAR name = "Version">
                                    <STRING>&quot;1.0.0 a&quot;</STRING>
                                </VAR>
                                <VAR name = "STKVersion">
                                    <INT>1160</INT>
                                </VAR>
                                <VAR name = "ComponentName">
                                    <STRING>&quot;ITU-R_P531-13&quot;</STRING>
                                </VAR>
                                <VAR name = "Description">
                                    <STRING>&quot;ITU-R P531-13&quot;</STRING>
                                </VAR>
                                <VAR name = "Type">
                                    <STRING>&quot;ITU-R P531-13&quot;</STRING>
                                </VAR>
                                <VAR name = "UserComment">
                                    <STRING>&quot;ITU-R P531-13&quot;</STRING>
                                </VAR>
                                <VAR name = "ReadOnly">
                                    <BOOL>false</BOOL>
                                </VAR>
                                <VAR name = "Clonable">
                                    <BOOL>true</BOOL>
                                </VAR>
                                <VAR name = "Category">
                                    <STRING>&quot;&quot;</STRING>
                                </VAR>
                                <VAR name = "UseAlternateAPFile">
                                    <BOOL>false</BOOL>
                                </VAR>
                                <VAR name = "AlternateAPDataFile">
                                    <STRING>
                                        <PROP name = "FullName">
                                            <STRING>&quot;&quot;</STRING>
                                        </PROP>&quot;&quot;</STRING>
                                </VAR>
                            </SCOPE>
                        </VAR>
                    </VAR>
                    <VAR name = "UseRainModel">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "RainModel">
                        <VAR name = "ITU-R_P618-12">
                            <SCOPE Class = "RainLossModel">
                                <VAR name = "Version">
                                    <STRING>&quot;1.0.0 a&quot;</STRING>
                                </VAR>
                                <VAR name = "STKVersion">
                                    <INT>1160</INT>
                                </VAR>
                                <VAR name = "ComponentName">
                                    <STRING>&quot;ITU-R_P618-12&quot;</STRING>
                                </VAR>
                                <VAR name = "Description">
                                    <STRING>&quot;ITU-R P618-12 rain model&quot;</STRING>
                                </VAR>
                                <VAR name = "Type">
                                    <STRING>&quot;ITU-R P618-12&quot;</STRING>
                                </VAR>
                                <VAR name = "UserComment">
                                    <STRING>&quot;ITU-R P618-12 rain model&quot;</STRING>
                                </VAR>
                                <VAR name = "ReadOnly">
                                    <BOOL>false</BOOL>
                                </VAR>
                                <VAR name = "Clonable">
                                    <BOOL>true</BOOL>
                                </VAR>
                                <VAR name = "Category">
                                    <STRING>&quot;&quot;</STRING>
                                </VAR>
                                <VAR name = "SurfaceTemperature">
                                    <QUANTITY Dimension = "Temperature" Unit = "K">
                                        <REAL>273.15</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "EnableDepolarizationLoss">
                                    <BOOL>false</BOOL>
                                </VAR>
                            </SCOPE>
                        </VAR>
                    </VAR>
                    <VAR name = "UseAtmosAbsorptionModel">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "AtmosAbsorptionModel">
                        <VAR name = "ITU-R_P676-9">
                            <SCOPE Class = "AtmosphericAbsorptionModel">
                                <VAR name = "Version">
                                    <STRING>&quot;1.0.1 a&quot;</STRING>
                                </VAR>
                                <VAR name = "STKVersion">
                                    <INT>1160</INT>
                                </VAR>
                                <VAR name = "ComponentName">
                                    <STRING>&quot;ITU-R_P676-9&quot;</STRING>
                                </VAR>
                                <VAR name = "Description">
                                    <STRING>&quot;ITU-R P676-9 gaseous absorption model&quot;</STRING>
                                </VAR>
                                <VAR name = "Type">
                                    <STRING>&quot;ITU-R P676-9&quot;</STRING>
                                </VAR>
                                <VAR name = "UserComment">
                                    <STRING>&quot;ITU-R P676-9 gaseous absorption model&quot;</STRING>
                                </VAR>
                                <VAR name = "ReadOnly">
                                    <BOOL>false</BOOL>
                                </VAR>
                                <VAR name = "Clonable">
                                    <BOOL>true</BOOL>
                                </VAR>
                                <VAR name = "Category">
                                    <STRING>&quot;&quot;</STRING>
                                </VAR>
                                <VAR name = "UseApproxMethod">
                                    <BOOL>true</BOOL>
                                </VAR>
                                <VAR name = "UseSeasonalRegional">
                                    <BOOL>true</BOOL>
                                </VAR>
                            </SCOPE>
                        </VAR>
                    </VAR>
                    <VAR name = "UseUrbanTerresPropLossModel">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "UrbanTerresPropLossModel">
                        <VAR name = "Two_Ray">
                            <SCOPE Class = "UrbanTerrestrialPropagationLossModel">
                                <VAR name = "Version">
                                    <STRING>&quot;1.0.0 a&quot;</STRING>
                                </VAR>
                                <VAR name = "STKVersion">
                                    <INT>1160</INT>
                                </VAR>
                                <VAR name = "ComponentName">
                                    <STRING>&quot;Two_Ray&quot;</STRING>
                                </VAR>
                                <VAR name = "Description">
                                    <STRING>&quot;Two Ray (Fourth Power Law) atmospheric absorption model&quot;</STRING>
                                </VAR>
                                <VAR name = "Type">
                                    <STRING>&quot;Two Ray&quot;</STRING>
                                </VAR>
                                <VAR name = "UserComment">
                                    <STRING>&quot;Two Ray (Fourth Power Law) atmospheric absorption model&quot;</STRING>
                                </VAR>
                                <VAR name = "ReadOnly">
                                    <BOOL>false</BOOL>
                                </VAR>
                                <VAR name = "Clonable">
                                    <BOOL>true</BOOL>
                                </VAR>
                                <VAR name = "Category">
                                    <STRING>&quot;&quot;</STRING>
                                </VAR>
                                <VAR name = "SurfaceTemperature">
                                    <QUANTITY Dimension = "Temperature" Unit = "K">
                                        <REAL>273.15</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "LossFactor">
                                    <REAL>1</REAL>
                                </VAR>
                            </SCOPE>
                        </VAR>
                    </VAR>
                    <VAR name = "UseCustomA">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "UseCustomB">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "UseCustomC">
                        <BOOL>false</BOOL>
                    </VAR>
                </SCOPE>
            </VAR>
        </VAR>
        <VAR name = "EarthTemperature">
            <QUANTITY Dimension = "Temperature" Unit = "K">
                <REAL>290</REAL>
            </QUANTITY>
        </VAR>
        <VAR name = "RainOutagePercent">
            <PROP name = "FormatString">
                <STRING>&quot;%#6.3f&quot;</STRING>
            </PROP>
            <REAL>0.1</REAL>
        </VAR>
        <VAR name = "ActiveCommSystem">
            <LINKTOOBJ>
                <STRING>&quot;None&quot;</STRING>
            </LINKTOOBJ>
        </VAR>
    </SCOPE>
</VAR>        END RfEnv

        BEGIN CommRad
        END CommRad

        BEGIN RadarCrossSection
<?xml version = "1.0" standalone = "yes"?>
<VAR name = "STK_Radar_RCS_Extension">
    <SCOPE Class = "RadarRCSExtension">
        <VAR name = "Version">
            <STRING>&quot;1.0.0 a&quot;</STRING>
        </VAR>
        <VAR name = "STKVersion">
            <INT>1160</INT>
        </VAR>
        <VAR name = "ComponentName">
            <STRING>&quot;STK_Radar_RCS_Extension&quot;</STRING>
        </VAR>
        <VAR name = "Description">
            <STRING>&quot;STK Radar RCS Extension&quot;</STRING>
        </VAR>
        <VAR name = "Type">
            <STRING>&quot;STK Radar RCS Extension&quot;</STRING>
        </VAR>
        <VAR name = "UserComment">
            <STRING>&quot;STK Radar RCS Extension&quot;</STRING>
        </VAR>
        <VAR name = "ReadOnly">
            <BOOL>false</BOOL>
        </VAR>
        <VAR name = "Clonable">
            <BOOL>true</BOOL>
        </VAR>
        <VAR name = "Category">
            <STRING>&quot;&quot;</STRING>
        </VAR>
        <VAR name = "Model">
            <VAR name = "Radar_Cross_Section">
                <SCOPE Class = "RCS">
                    <VAR name = "Version">
                        <STRING>&quot;1.0.0 a&quot;</STRING>
                    </VAR>
                    <VAR name = "STKVersion">
                        <INT>1160</INT>
                    </VAR>
                    <VAR name = "ComponentName">
                        <STRING>&quot;Radar_Cross_Section&quot;</STRING>
                    </VAR>
                    <VAR name = "Description">
                        <STRING>&quot;Radar Cross Section&quot;</STRING>
                    </VAR>
                    <VAR name = "Type">
                        <STRING>&quot;Radar Cross Section&quot;</STRING>
                    </VAR>
                    <VAR name = "UserComment">
                        <STRING>&quot;Radar Cross Section&quot;</STRING>
                    </VAR>
                    <VAR name = "ReadOnly">
                        <BOOL>false</BOOL>
                    </VAR>
                    <VAR name = "Clonable">
                        <BOOL>true</BOOL>
                    </VAR>
                    <VAR name = "Category">
                        <STRING>&quot;&quot;</STRING>
                    </VAR>
                    <VAR name = "FrequencyBandList">
                        <LIST>
                            <SCOPE>
                                <VAR name = "MinFrequency">
                                    <QUANTITY Dimension = "BandwidthUnit" Unit = "Hz">
                                        <REAL>2997920</REAL>
                                    </QUANTITY>
                                </VAR>
                                <VAR name = "ComputeTypeStrategy">
                                    <VAR name = "Constant Value">
                                        <SCOPE Class = "RCS Compute Strategy">
                                            <VAR name = "ConstantValue">
                                                <QUANTITY Dimension = "RcsUnit" Unit = "sqm">
                                                    <REAL>1</REAL>
                                                </QUANTITY>
                                            </VAR>
                                            <VAR name = "Type">
                                                <STRING>&quot;Constant Value&quot;</STRING>
                                            </VAR>
                                            <VAR name = "ComponentName">
                                                <STRING>&quot;Constant Value&quot;</STRING>
                                            </VAR>
                                        </SCOPE>
                                    </VAR>
                                </VAR>
                                <VAR name = "SwerlingCase">
                                    <STRING>&quot;0&quot;</STRING>
                                </VAR>
                            </SCOPE>
                        </LIST>
                    </VAR>
                </SCOPE>
            </VAR>
        </VAR>
    </SCOPE>
</VAR>        END RadarCrossSection

        BEGIN RadarClutter
<?xml version = "1.0" standalone = "yes"?>
<VAR name = "STK_Radar_Clutter_Extension">
    <SCOPE Class = "RadarClutterExtension">
        <VAR name = "Version">
            <STRING>&quot;1.0.0 a&quot;</STRING>
        </VAR>
        <VAR name = "STKVersion">
            <INT>1160</INT>
        </VAR>
        <VAR name = "ComponentName">
            <STRING>&quot;STK_Radar_Clutter_Extension&quot;</STRING>
        </VAR>
        <VAR name = "Description">
            <STRING>&quot;STK Radar Clutter Extension&quot;</STRING>
        </VAR>
        <VAR name = "Type">
            <STRING>&quot;STK Radar Clutter Extension&quot;</STRING>
        </VAR>
        <VAR name = "UserComment">
            <STRING>&quot;STK Radar Clutter Extension&quot;</STRING>
        </VAR>
        <VAR name = "ReadOnly">
            <BOOL>false</BOOL>
        </VAR>
        <VAR name = "Clonable">
            <BOOL>true</BOOL>
        </VAR>
        <VAR name = "Category">
            <STRING>&quot;&quot;</STRING>
        </VAR>
        <VAR name = "ClutterMap">
            <VAR name = "Constant Coefficient">
                <SCOPE Class = "Clutter Map">
                    <VAR name = "ClutterCoefficient">
                        <QUANTITY Dimension = "RatioUnit" Unit = "units">
                            <REAL>1</REAL>
                        </QUANTITY>
                    </VAR>
                    <VAR name = "Type">
                        <STRING>&quot;Constant Coefficient&quot;</STRING>
                    </VAR>
                    <VAR name = "ComponentName">
                        <STRING>&quot;Constant Coefficient&quot;</STRING>
                    </VAR>
                </SCOPE>
            </VAR>
        </VAR>
    </SCOPE>
</VAR>        END RadarClutter

        BEGIN Gator
        END Gator

        BEGIN Crdn
        END Crdn

        BEGIN SpiceExt
        END SpiceExt

        BEGIN FlightScenExt
        END FlightScenExt

        BEGIN DIS

            BEGIN General

                Verbose		 Off
                Processing		 Off
                Statistics		 Off
                ExerciseID		 -1
                ForceID		 -1

            END General


            BEGIN Output

                Version		 5
                ExerciseID		 1
                forceID		 1
                HeartbeatTimer		 5
                DistanceThresh		 1
                OrientThresh		 3

            END Output


            BEGIN Time

                Mode		 rtPDUTimestamp

            END Time


            BEGIN PDUInfo


            END PDUInfo


            BEGIN Parameters

                ParmData		 COLORFRIENDLY blue
                ParmData		 COLORNEUTRAL white
                ParmData		 COLOROPFORCE red
                ParmData		 MAXDRELSETS 1000

            END Parameters


            BEGIN Network

                NetIF		 Default
                Mode		 Broadcast
                McastIP		 224.0.0.1
                Port		 3000
                rChannelBufferSize		 65000
                ReadBufferSize		 1500
                QueuePollPeriod		 20
                MaxRcvQueueEntries		 1000
                MaxRcvIOThreads		 4
                sChannelBufferSize		 65000

            END Network


            BEGIN EntityTypeDef


# order: kind:domain:country:catagory:subCatagory:specific:xtra ( -1 = * )


            END EntityTypeDef


            BEGIN EntityFilter
                Include		 *:*:*
            END EntityFilter

        END DIS

    END Extensions

    BEGIN SubObjects

        Class AreaTarget

            YRD_000		
            YRD_001		
            YRD_002		

        END Class

        Class CoverageDefinition

            GlobalAll		
            GlobalReachable		
            YRD_GridDiagnostic		

        END Class

        Class Satellite

            SAT_001		
            SAT_002		
            SAT_003		
            SAT_004		
            SAT_005		
            SAT_006		
            SAT_007		
            SAT_008		
            SAT_009		
            SAT_010		
            SAT_011		
            SAT_012		
            SAT_013		
            SAT_014		
            SAT_015		
            SAT_016		
            SAT_017		
            SAT_018		
            SAT_019		
            SAT_020		
            SAT_021		
            SAT_022		
            SAT_023		
            SAT_024		
            SAT_025		
            SAT_026		
            SAT_027		
            SAT_028		

        END Class

    END SubObjects

    BEGIN References
        Instance *
            *		
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
        END Instance
        Instance AreaTarget/YRD_000
            AreaTarget/YRD_000		
        END Instance
        Instance AreaTarget/YRD_001
            AreaTarget/YRD_001		
        END Instance
        Instance AreaTarget/YRD_002
            AreaTarget/YRD_002		
        END Instance
        Instance CoverageDefinition/GlobalAll
            CoverageDefinition/GlobalAll		
        END Instance
        Instance CoverageDefinition/GlobalReachable
            CoverageDefinition/GlobalReachable		
        END Instance
        Instance CoverageDefinition/YRD_GridDiagnostic
            CoverageDefinition/YRD_GridDiagnostic		
        END Instance
        Instance Satellite/SAT_001
            Satellite/SAT_001		
            Satellite/SAT_001/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_001/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_001/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_002
            Satellite/SAT_002		
            Satellite/SAT_002/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_002/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_002/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_003
            Satellite/SAT_003		
            Satellite/SAT_003/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_003/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_003/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_004
            Satellite/SAT_004		
            Satellite/SAT_004/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_004/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_004/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_005
            Satellite/SAT_005		
            Satellite/SAT_005/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_005/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_005/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_006
            Satellite/SAT_006		
            Satellite/SAT_006/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_006/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_006/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_007
            Satellite/SAT_007		
            Satellite/SAT_007/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_007/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_007/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_008
            Satellite/SAT_008		
            Satellite/SAT_008/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_008/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_008/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_009
            Satellite/SAT_009		
            Satellite/SAT_009/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_009/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_009/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_010
            Satellite/SAT_010		
            Satellite/SAT_010/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_010/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_010/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_011
            Satellite/SAT_011		
            Satellite/SAT_011/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_011/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_011/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_012
            Satellite/SAT_012		
            Satellite/SAT_012/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_012/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_012/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_013
            Satellite/SAT_013		
            Satellite/SAT_013/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_013/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_013/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_014
            Satellite/SAT_014		
            Satellite/SAT_014/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_014/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_014/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_015
            Satellite/SAT_015		
            Satellite/SAT_015/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_015/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_015/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_016
            Satellite/SAT_016		
            Satellite/SAT_016/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_016/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_016/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_017
            Satellite/SAT_017		
            Satellite/SAT_017/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_017/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_017/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_018
            Satellite/SAT_018		
            Satellite/SAT_018/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_018/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_018/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_019
            Satellite/SAT_019		
            Satellite/SAT_019/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_019/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_019/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_020
            Satellite/SAT_020		
            Satellite/SAT_020/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_020/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_020/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_021
            Satellite/SAT_021		
            Satellite/SAT_021/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_021/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_021/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_022
            Satellite/SAT_022		
            Satellite/SAT_022/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_022/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_022/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_023
            Satellite/SAT_023		
            Satellite/SAT_023/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_023/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_023/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_024
            Satellite/SAT_024		
            Satellite/SAT_024/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_024/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_024/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_025
            Satellite/SAT_025		
            Satellite/SAT_025/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_025/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_025/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_026
            Satellite/SAT_026		
            Satellite/SAT_026/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_026/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_026/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_027
            Satellite/SAT_027		
            Satellite/SAT_027/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_027/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_027/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_028
            Satellite/SAT_028		
            Satellite/SAT_028/Sensor/Cam		
        END Instance
        Instance Satellite/SAT_028/Sensor/Cam
            CoverageDefinition/GlobalAll		
            CoverageDefinition/GlobalReachable		
            CoverageDefinition/YRD_GridDiagnostic		
            Satellite/SAT_028/Sensor/Cam		
        END Instance
    END References

END Scenario
