/**************************************************************************
* 版    权： 	Copyright (c) 2015 
* 文件名称：	Net_Interface.h
* 文件标识： 
* 内容摘要：    摄像机网络开发SDK,处理视频流、图片及控制消息
* 其它说明： 
* 当前版本：	V1.0
* 作    者	
* 完成日期：	2013年08月28日
**************************************************************************/
#ifndef __DCINTERFACE_H
#define __DCINTERFACE_H

#ifdef     NET_API
#else
   #define NET_API __declspec(dllimport)
#endif

#include "Net_Setup.h"
#ifdef __cplusplus
extern "C"
{
#endif

/**************************************************************************
 *                         数据类型                                    *
 **************************************************************************/

#define LENS_MAX_STEPS  2284/4/2
#define MAX_PAY_ITEM       		        4
#define MAX_TIMESECTION_NUM		 6	
typedef enum
{
	LIGHT_MODE_CLOSE = 0,
	LIGHT_MODE_OPEN,
	LIGHT_MODE_AUTO,
	LIGHT_MODE_ALL,
}E_LightMode;

typedef enum 
{ 
	WL_MODE_UNKNOW = 0, 
	WL_MODE_OFFLINE,	 /*脱机使能*/ 
	WL_MODE_ENABLE,	 /*白名单使能，不分区联机、脱机*/ 
	WL_MODE_DISABLE,	 /*白名单不使能*/ 
	WL_MODE_MAX 
}E_WhiteListMode; 

typedef struct
{
	unsigned char ucMode;
	unsigned char ucArmyPoliceEn; /*军警牌自动放行使能标识*/ 
	unsigned char ucNotSnaptmp;/*脱机下不保存临时车记录*/
	unsigned char acReserved;
}T_WhiteListMode;

typedef enum
{
	LED_SUB_MOD_VEH_PLATE=0,/*车牌显示*/
	LED_SUB_MOD_VEH_WELCOME,/*欢迎语显示*/
	LED_SUB_MOD_VEH_PAY,  /*停车付费显示*/
	LED_SUB_MOD_VEH_TIME, /*停车时间显示*/
	LED_SUB_MOD_VEH_PERIOD, /*月租有效期显示*/
	LED_SUB_MOD_TIME,/*时间显示，格式:XXXX年XX月XX时XX分*/
	LED_SUB_MOD_VEH_LEFT,/*剩余停车位显示*/
	LED_SUB_MOD_CUSTOM,  /*自定义内容显示*/
	LED_SUB_MOD_MAX,
}E_SubLedMode;

typedef struct
{
	unsigned char 	ucEnable;
	unsigned char  	ucInterval;//时间间隔  s秒
	unsigned char   ucLedLine;//双行屏，上行1；下行2;
	unsigned char   ucMode;//E_SubLedMode
	unsigned char   aucContent[MAX_LED_CONTENT]; //GB2312，自定义模式有效
}T_SubLedSetup;

typedef struct
{
	//unsigned char           ucType;//入口空闲-0; 入口忙-1; 出口空闲-2; 出口忙-3;
	unsigned char           ucAudioEnable;
	unsigned char           ucReserved[3];
	T_SubLedSetup   atSubLedInIdle[MAX_LED_COUNT];//入口空闲
	T_SubLedSetup   atSubLedInBusy[MAX_LED_COUNT];//入口忙  
	T_SubLedSetup   atSubLedOutIdle[MAX_LED_COUNT];//出口空闲
	T_SubLedSetup   atSubLedOutBusy[MAX_LED_COUNT];//出口忙
}T_LedSetup;

typedef enum _E_LED_COLOR
{
	E_LED_COLOR_RED = 0,
	E_LED_COLOR_GREEN,
	E_LED_COLOR_YELLOW
}E_LED_COLOR;

//#define MAX_LED_CONTENT         64
#define MAX_LZ_LED_COUNT         4
#define MAX_VEL_CONTENT         32

typedef struct
{
	unsigned char 	ucEnable;
	unsigned char  	ucInterval;		//时间间隔  s秒
	unsigned char   ucLedLine;		//(保留不用)
	unsigned char   ucLedcolor;  	//E_LED_COLOR
	unsigned short  usModeBit;		
	unsigned char  ucReserved[2];
	unsigned char  welAudioText[MAX_VEL_CONTENT]; 	//GB2312，压地感报欢迎语
	unsigned char  levAudioText[MAX_VEL_CONTENT]; 	//GB2312，开闸报欢迎语
	unsigned char  aucContent[MAX_LED_CONTENT]; //GB2312，自定义模式有效
}T_LZ_SubLedSetup;

typedef struct
{
	//unsigned char           ucType;//入口空闲-0; 入口忙-1; 出口空闲-2; 出口忙-3;
	unsigned char   ucAudioEnable;
	unsigned char   ucReserved[3];
	T_LZ_SubLedSetup   atSubLedIdle[MAX_LZ_LED_COUNT];//空闲
	T_LZ_SubLedSetup   atSubLedBusy[MAX_LZ_LED_COUNT];//忙  
}T_LZ_LedSetup;

typedef struct
{
	unsigned char   ucLedSubType;  //E_LedScreenSubType
	unsigned char   ucReserved[3];
	char			acInContent[MAX_LED_CONTENT]; //GB2312，自定义模式有效
	char			acOutContent[MAX_LED_CONTENT]; //GB2312，自定义模式有效
}T_DCScreenSetup;

/*帧信息*/
#ifndef _T_FRAMEINFO_
#define _T_FRAMEINFO_
typedef struct
{
	unsigned int uiFrameId;          //帧ID
	unsigned int uiTimeStamp;        //RTP时间戳
	unsigned int uiEncSize;          //帧大小
	unsigned int uiFrameType;        // 1:i帧 0:其它

}T_FrameInfo;
#endif

typedef struct
{
	unsigned int	uiImageId;
	unsigned char   ucLightIndex;	/*车道编号，1~25,与相机的车道设置一致*/
	unsigned char   ucLightMode;	/*E_LightMode*/
	unsigned short  usGroupId;
}T_DCImageSnap;

typedef enum
{
	COLOR_TYPE_BLUE = 0,
	COLOR_TYPE_YELLO,
	COLOR_TYPE_WHITE,
	COLOR_TYPE_BLACK,
	COLOR_TYPE_OTHER,
	COLOR_TYPE_GREEN,
	COLOR_TYPE_YELLOW_GREEN,
	COLOR_TYPE_ALL, 
}E_ColorType;

typedef enum
{
	VEHCOLOR_UNKNOW = 0,/*未知*/
	VEHCOLOR_WHITE = 1,/* 白*/
	VEHCOLOR_BLACK = 2,/* 黑*/
	VEHCOLOR_RED = 3,/* 红*/
	VEHCOLOR_BLUE = 4,/* 蓝*/
	VEHCOLOR_YELLOW = 5,/* 黄*/
	VEHCOLOR_GRAY = 6,/* 灰*/
	VEHCOLOR_GREEN = 7,/* 绿*/
	VEHCOLOR_LIGHT_RED = 8,/*浅红*/
	VEHCOLOR_LIGHT_BLUE = 9,/*浅蓝*/
	VEHCOLOR_LIGHT_YELLOW = 10,/*浅黄*/
	VEHCOLOR_LIGHT_GRAY = 11,/*浅灰*/
	VEHCOLOR_LIGHT_GREEN = 12,/*浅绿*/
	VEHCOLOR_DARK_BROWN = 13,/*深棕*/
	VEHCOLOR_DARK_PINK = 14,	/*深粉*/
	VEHCOLOR_LIGHT_BROWN = 15,/*浅棕*/
	VEHCOLOR_LIGHT_PINK = 16, /*浅粉*/
	VEHCOLOR_DARK_RED = 17,/*深红*/
	VEHCOLOR_DARK_BLUE = 18,/*深蓝*/
	VEHCOLOR_DARK_YELLOW = 19,/*深黄*/
	VEHCOLOR_DARK_GRAY = 20,/*深灰*/
	VEHCOLOR_DARK_GREEN = 21,/*深绿*/
	VEHCOLOR_ALL,
}E_VehColorType;


//车标信息
typedef enum
{
	UNKNOWN_FLAG,
	TOYOTA,        /*丰田*/
	VolksWagen,    /*大众*/
	HONDA,         /*本田*/
	PEUGEOT,       /*标致*/
	HYUNDAI,       /*现代*/
	BUICK,         /*别克*/
	AUDI,          /*奥迪*/
	KIA,           /*起亚*/
	JEEP,          /*吉普*/
	FORD,          /*福特*/
	BENZ,          /*奔驰*/
	BMW,           /*宝马*/
	MAZDA,         /*马自达*/
	SUZUKI,        /*铃木*/
	CITROEN,       /*雪铁龙*/
	NISSAN,        /*尼桑*/
	MITSUBISHI,    /*三菱*/
	LEXUS,         /*雷克萨斯*/
	CHEVROLET,     /*雪佛兰*/
	VOLVO,         /*沃尔沃*/
	FIAT,          /*菲亚特*/
	BYD,           /*比亚迪*/
	CHERY          /*奇瑞*/
}E_VehicleFlag;

//车型信息
typedef enum
{
	VEHICLE_TYPE_UNKNOW = 0,
	VEHICLE_TYPE_BIG_BUS,   			// 大巴1
	VEHICLE_TYPE_MEDIUM_BUS,  			// 中巴2
	VEHICLE_TYPE_CAR_SUV,   			// 小汽车3
	VEHICLE_TYPE_SMALL_BUS,   			// 小巴4
	VEHICLE_TYPE_TRUCK,  				// 卡车5
	VEHICLE_TYPE_MAX
}E_VehicleType;

/*车身颜色*/
typedef enum
{
	VEHICLE_COLOR_UNKNOW = 0,
	VEHICLE_COLOR_BLACK,  				// 黑色1
	VEHICLE_COLOR_BLUE,   				// 蓝色2
	VEHICLE_COLOR_BROWN,  				// 棕色3
	VEHICLE_COLOR_GRAY,   				// 灰色4
	VEHICLE_COLOR_GREEN,  				// 绿色5
	VEHICLE_COLOR_PURPLE, 				// 紫色6
	VEHICLE_COLOR_RED,    				// 红色7
	VEHICLE_COLOR_WHITE,  				// 白色8
	VEHICLE_COLOR_YELLOW, 				// 黄色9
	VEHICLE_COLOR_MAX
}E_VehicleColorx;

typedef enum
{
	VIO_CODE_NORMAL = 0,  		/*正常车辆*/
	VIO_CODE_BLACKLIST,    		/*黑名单车辆*/
	VIO_CODE_OVERSPEED_LITTLE,	/*超速50%以内*/
	VIO_CODE_OVERSPEED_MID,		/*超速50%~100%*/
	VIO_CODE_OVERSPEED_MORE,    /*超速100%以上*/
	VIO_CODE_RETROGRADE,   		/*逆行*/
	VIO_CODE_RUSH_REDLIGHT,		/*闯红灯*/
	VIO_CODE_LOWSPEED, 			/*低速行驶*/
	VIO_CODE_PROHIBIT,			/*禁行*/
	VIO_CODE_EXCEED,			/*越线*/
	VIO_CODE_ABNORMAL_STEER,	/*不按车道行驶*/
	VIO_CODE_ILLEGAL_STOP,      /*违停*/
	VIO_CODE_FACE_MAIN,         /*人脸大图*/
	VIO_CODE_FACE,              /*人脸*/
	VIO_CODE_ALL,
}E_ViolationCode;

/* 行车方向定义 */
typedef enum
{
	EAST_TO_WEST = 0,
	WEST_TO_EAST,
	SOUTH_TO_NORTH,
	NORTH_TO_SOUTH
}E_Direction;

/*视频桩车位状态*/
typedef enum
{
	VIDEO_PILE_IDLE = 0,	//空闲
	VIDEO_PILE_CAR,			//有车
	VIDEO_PILE_LINE,		//压线
	VIDEO_PILE_SPECIAL_CAR,	//特殊车位
	VIDEO_PILE_MAX
}E_DirectionVideoPile;

typedef enum
{
	CONN_STATE_UNKNOW = 0, 
	CONN_STATE_TRYING, 		/*连接中*/
	CONN_STATE_SUCC,		/*连接成功*/
	CONN_STATE_DIS,			/*连接失败*/
	CONN_STATE_ALL,
}E_ConnState;

typedef enum 
{ 
	SNAP_MODE_UNKNOW = 0, 
	SNAP_MODE_MANUAL,	 /*手动*/ 
	SNAP_MODE_VIDEO,     /*视频*/ 
	SNAP_MODE_LOOP,      /*线圈*/ 
	SNAP_MODE_MAX, 
}E_SnapType;

typedef enum its_ep_pt
{
	EP_PLATE_TYPE_NULL=0,      //未知
	EP_PLATE_TYPE_BLUE,        //普通蓝牌
	EP_PLATE_TYPE_BLACK,       //普通黑牌
	EP_PLATE_TYPE_YELL,        //普通黄牌
	EP_PLATE_TYPE_YELL2,       //双层黄牌
	EP_PLATE_TYPE_POL,         //警察车牌
	EP_PLATE_TYPE_APOL,        //武警车牌
	EP_PLATE_TYPE_APOL2,       //双层武警    
	EP_PLATE_TYPE_ARM,         //单层军牌
	EP_PLATE_TYPE_ARM2,        //双层军牌
	EP_PLATE_TYPE_INDI,        //个性车牌
	EP_PLATE_TYPE_NEWN,        //新能源小车牌
	EP_PLATE_TYPE_NEWN1,       //新能源大车牌
	EP_PLATE_TYPE_EMB,         //大使馆车牌
	EP_PLATE_TYPE_CON,         //领事馆车牌
	EP_PLATE_TYPE_MIN,         //民航车牌
}ITS_Ep_Pt;

typedef enum
{
	IPNC_TYPE_UNKNOW = 0,
	IPNC_TYPE_ENTRY,
	IPNC_TYPE_EXIT,
	IPNC_TYPE_PLATE_REC,  /*车牌识别相机*/
	IPNC_TYPE_MAX,     
}E_IpncType;

/*车辆图片抓拍信息*/
typedef struct 
{
	unsigned short 	usWidth;   /*图片的宽度，单位:像素*/
	unsigned short	usHeight;  /*图片的高度，单位:像素*/
	unsigned char	ucVehicleColor;/*车身颜色，E_VehicleColorx*/
	unsigned char	ucVehicleBrand;/*车标，E_VehicleFlag*/
	unsigned char	ucVehicleSize;/*车型(1大2中3小)，E_VehicleType,目前根据车牌颜色来区分大小车，蓝牌为小车，黄牌为大车*/
	unsigned char	ucPlateColor;/*车牌颜色，E_ColorType*/
	char  			szLprResult[16];/*车牌，若为'\0'，表示无效GB2312编码*/
	unsigned short	usLpBox[4];  /*车牌位置，左上角(0, 1), 右下角(2,3)*/
	unsigned char	ucLprType;/*车牌类型, ITS_Ep_Pt*/
	unsigned short 	usSpeed;     /*单位km/h*/
	unsigned char 	ucSnapType;  /*抓拍模式, E_SnapType*/
	unsigned char 	ucHaveVehicle;			/*0未知1异常2正常*/
	char 			acSnapTime[18];         /*图片抓拍时间:格式YYYYMMDDHHMMSSmmm(年月日时分秒毫秒)*/
	
	unsigned char	ucViolateCode;    /*违法代码E_ViolationCode*/
	unsigned char	ucLaneNo;          /*车道号,从0开始编码*/
	unsigned int 	uiVehicleId; 		/*检测到的车辆id，若为同一辆车，则id相同*/
	unsigned char	ucScore;    		/*车牌识别可行度*/
	unsigned char	ucDirection;       /*行车方向E_Direction,充电桩对应E_LOCKCARRUNDIRECTION,视频桩车位状态E_DirectionVideoPile*/
	unsigned char	ucTotalNum;        /*该车辆抓拍总张数*/
	unsigned char	ucSnapshotIndex;   /*当前抓拍第几张，从0开始编号*/
}T_ImageUserInfo;

/*车辆图片抓拍信息*/
typedef struct 
{
	unsigned short 	usWidth;   /*图片的宽度，单位:像素*/
	unsigned short	usHeight;  /*图片的高度，单位:像素*/
	unsigned char	ucVehicleColor;/*车身颜色，E_VehicleColorx*/
	unsigned char	ucVehicleBrand;/*车标，E_VehicleFlag*/
	unsigned char	ucVehicleSize;/*车型(1大2中3小)，E_VehicleType,目前根据车牌颜色来区分大小车，蓝牌为小车，黄牌为大车*/
	unsigned char	ucPlateColor;/*车牌颜色，E_ColorType*/
	char  			szLprResult[16];/*车牌，若为'\0'，表示无效GB2312编码*/
	unsigned short	usLpBox[4];  /*车牌位置，左上角(0, 1), 右下角(2,3)*/
	unsigned char	ucLprType;/*车牌类型, ITS_Ep_Pt*/
	unsigned short 	usSpeed;     /*单位km/h*/
	unsigned char 	ucSnapType;  /*抓拍模式, E_SnapType*/
	unsigned char 	ucHaveVehicle;			/*0未知1异常2正常*/
	char 			acSnapTime[18];         /*图片抓拍时间:格式YYYYMMDDHHMMSSmmm(年月日时分秒毫秒)*/

	unsigned char	ucViolateCode;    /*违法代码E_ViolationCode*/
	unsigned char	ucLaneNo;          /*车道号,从0开始编码*/
	unsigned int 	uiVehicleId; 		/*检测到的车辆id，若为同一辆车，则id相同*/
	unsigned char	ucScore;    		/*车牌识别可行度*/
	unsigned char	ucDirection;       /*行车方向E_Direction,充电桩对应E_Lock_CarRunDirection,视频桩车位状态E_DirectionVideoPile*/
	unsigned char	ucTotalNum;        /*该车辆抓拍总张数*/
	unsigned char	ucSnapshotIndex;   /*当前抓拍第几张，从0开始编号*/

	unsigned int 	uiVideoProcTime;   /*摄像头从触发拍照到上传车牌的用时，单位ms*/
	char			strVehicleBrand[128]; /*车型品牌*/
	char			strConfidence[12];	  /*车型可信度*/
	char			strSpecialCode[20][12]; /*特征码*/
	char			ucHasCar;				/*是否有车*/
	unsigned short	aucReservedYWC;
	char			aucReserved1;		/*保留字段*/
	char	acParkingNo[16];	/*充电桩 车位编号*/
	unsigned char   aucReserved2[236];		/*保留字段*/
}T_ImageUserInfo2;

/*车辆详细信息，相机单独上报时用到*/
typedef struct
{
	unsigned char	ucVehicleColor;/*车身颜色，E_ColorType*/
	unsigned char 	ucHaveVehicle;	/*0未知1异常2正常*/
	unsigned char	ucVehicleSize;/*车型(1大2中3小)，ITS_Tb_Vt,目前根据车牌颜色来区分大小车，蓝牌为小车，黄牌为大车*/
	unsigned char	ucPlateColor;/*车牌颜色，E_ColorType*/

	unsigned short	ucVehicleBrand;/*车标，E_VehicleFlag*/
	unsigned char	ucDirection;       /*行车方向E_Direction*/
	unsigned char   ucBright;// 预留

	char  			szLprResult[16];/*车牌，若为'\0'，表示无效GB2312编码*/
	unsigned short	usLpBox[4];  /*车牌位置，左上角(0, 1), 右下角(2,3)*/
	unsigned int 	uiVehicleId; 		/*检测到的车辆id，若为同一辆车，则id相同*/
	unsigned int 	usSpeed;     /*单位km/h*/

	unsigned char	uaReserved[8];    	// 预留	
	unsigned char	ucScore;    		/*车牌识别可信度*/
	unsigned char	ucLprType;/*车牌类型*/
	unsigned char 	ucSnapType;  /*抓拍模式, E_SnapType*/
	unsigned char	ucLaneNo;    /*车道号,从0开始编码,暂时未用到*/

	char			acSnapTime[18]; 		/*图片抓拍时间:格式YYYYMMDDHHMMSSmmm(年月日时分秒毫秒)*/
	unsigned char	uaReserved2[256];    	// 预留
}T_Lprinfo_ext;

//车的运动方向
typedef enum
{
	CAR_RUN_DIRECTION_KEEP,//车不动
	CAR_RUN_DIRECTION_COME,//车进场 
	CAR_RUN_DIRECTION_OUT,//车离开
	CAR_RUN_DIRECTION_BLOCK,//车辆遮挡
	CAR_RUN_DIRECTION_IDLE,//车位空闲
	CAR_RUN_DIRECTION_MAX
}E_Lock_CarRunDirection;
/*车的状态*/
typedef enum
{
	CAR_STATE_INIT,  // 初始化 0 
	CAR_STATE_IDLE,  // 空闲 1 
	CAR_STATE_ENTER, // 驶入 2
	CAR_STATE_STOP,  // 停稳   3
	CAR_STATE_EXIT, // 驶出 4
	CAR_STATE_LINE,	//压线 5
	CAR_STATE_MAX, 
}E_CarState;

/* 会员 类型*/
typedef enum
{
	TEMPORARY_CAR = 0,  	/* 临时车*/
	MOON_CAR,      	/* 月卡*/
	VIP_CAR,   		/* 贵宾卡*/
	STORED_CAR,  	/* 储值卡*/
	LEAD_CAR,      	/* 领导车*/
	SPECIAL_CAR,   	/* 特殊车*/
	INSIDE_CAR ,  	/* 内部车*/
	WHITE_CAR,     	/* 白名单*/
	BLACK_CAR,  	 /* 黑名单*/
	MAX_CAR
} E_MemberType;


typedef struct
{
	char			acPlate[16];	 /* 车牌号码，GB2312编码 */
	char			acEntryTime[18]; /* 入场时间*/
	char			acExitTime[18]; /* 出场时间*/
	unsigned int	uiRequired;  /* 应付金额，0.1元为单位*/
	unsigned int	uiPrepaid;  	/* 已付金额，0.1元为单位*/
	unsigned char	ucVehType;  /* 车辆类型1小车2大车 E_ParkVehSize*/
	unsigned char	ucUserType;  /*会员类型E_MemberType*/
	char			ucResultCode; /* 收费结果状态码0 成功 1 没有找到入场记录*/
	char			acReserved;
}T_VehPayRsp;

typedef  struct
{
	unsigned  int		ParkNum;  
}T_ParkNum;

typedef  struct
{
	unsigned  short		usInYear;  
	unsigned  char		ucInMonth; 
	unsigned  char		ucInDay;  
	unsigned  char		ucInHour; 
	unsigned  char		ucInMinute; 
	unsigned  char		ucInSecond;
	unsigned  char		ucReserved1;
	unsigned  short		usOutYear;
	unsigned  char		ucOutMonth;
	unsigned  char		ucOutDay;
	unsigned  char		ucOutHour;
	unsigned  char		ucOutMinute;
	unsigned  char		ucOutSecond;
	unsigned  char		ucReserved2;
	unsigned  int		uiPayAmount; 
	unsigned  int		uiTimeLen;  
	char	 			acLrpResult[16]; 
}T_PayCount;

typedef enum
{
	GATE_STATE_UNKNOW = 0,
	GATE_STATE_OPEN,
	GATE_STATE_CLOSE,
	GATE_STATE_STOP,
	GATE_STATE_MAX
}E_GateState;

typedef  struct
{
	unsigned  char		ucState;    /*E_GateState*/
	unsigned  char		ucIndex;	/*表示0-4路IO输入索引*/
	unsigned  char		ucGateDefSta;/*非SDK使用，默认置0*/
	unsigned  char		ucReserved;  
}T_ControlGate;

typedef  struct
{
	unsigned  char		rs485Id;
	unsigned  char		ucReserved; 
	unsigned  short		dataLen; 
	unsigned  char		data[1024];
}T_RS485Data;

typedef struct
{
	unsigned int uiPanoramaPicLen;  /*全景图片大小*/
	unsigned int uiVehiclePicLen;      /*车牌图片大小*/
	unsigned char *ptPanoramaPicBuff;   /*全景图片缓冲区*/
	unsigned char *ptVehiclePicBuff;  /*车牌图片缓冲区*/
}T_PicInfo;

typedef struct
{
	unsigned char LprResult[16];/*车牌号码；单条消息最多80条车牌号码；其它分多条消息发送*/
	unsigned char StartTime[16];//eg:20151012190303 YYYYMMDDHHMMSS
	unsigned char EndTime[16];//eg:20151012190303 YYYYMMDDHHMMSS
}T_LprResult;

typedef enum
{
	ADD_PLATE_MODE,//新增，若该车牌已存在，则会自动覆盖
	DELETE_PLATE_MODE,//删除
	SEND_MODE_MAX
}E_SendLprMode;


typedef struct 
{
	unsigned char ucType;//E_SendLprMode
	unsigned char ucConut;//本次传输的车牌个数
	unsigned char LprMode;  /* 0：白名单；1：黑名单(为了兼容原有白名单)*/
	//unsigned char aucReserved[2];//保留位
	unsigned char aucReserved[1];//保留位
	T_LprResult	  atLprResult[10];//车牌信息
}T_SendLprByMess;

typedef struct  
{
	unsigned char ucResult; //查询的结果，0为未找到该车牌，1为成功找到该车牌
	unsigned char aucReserved[3];
	T_LprResult	  tLprResult;
}T_RspLprResult;
typedef struct
{
	int uiCount;  /* 当前准备写入白名单的车牌个数，即ptLprResult指向的待写入的车牌的个数*/
	char aucLplPath[256];
}T_BlackWhiteListCount;
typedef struct
{
	unsigned char LprMode;  /* 0：黑名单；1：白名单*/
	unsigned char LprCode;      /* 0：车牌号码utf-8字符编码；1：车牌号码gb2312字符编码*/
	unsigned char Lprnew; /*0： 重新发送；1：续传；2:删除；*/
	char aucLplPath[256];
}T_BlackWhiteList;


typedef struct
{
	unsigned char LprMode;  /* 0：黑名单；1：白名单*/
	unsigned char LprCode;      /* 0：车牌号码utf-8字符编码；1：车牌号码gb2312字符编码*/
	char aucLplPath[256];
}T_GetBlackWhiteList;
typedef enum
{
	REPORT_MESS_MAC,
	REPORT_MESS_ACE,
	REPORT_MESS_PARK_STATE,
	REPORT_MESS_RESET_KEY_PRESS,
	REPORT_MESS_VEH_INFO,
	REPORT_MESS_ASS_CAM_IP_SEARCH,
	REPORT_MESS_RS485_IN_DATA,
	REPORT_MESS_LOOP_DETECTOR,
	REPORT_VIDEO_DISTRICT_CHANGED,
	REPORT_TRA_STAT_REPORT,
	REPORT_ASS_CAMERA_TYPE,
	REPORT_FILE_RECV_STATE,
	REPORT_PS_PARKINGINFO,
	REPORT_PARK_NUM,
	REPORT_CKECK_TALKBACK_BNT,
	REPORT_4G_STATUS,
	REPORT_AUDIO_LINK,
	REPORT_WARNINGINFO,
	REPORT_CAM_CHECK_RESULT,
	REPORT_REMOTE_STATE,//上报远程链接状态
	REPORT_LPRINFO_EXT,	//单独上报车牌信息 不带图片
	REPORT_MESS_MAX
}E_ReportMess;
typedef struct
{
	unsigned char  acMac[18];      //eg: "xx:xx:xx:xx:xx:xx"
	unsigned char  acTime[18];     //eg:"YYYYMMDDHHMMSSxxx" 
}T_MacInfo;

typedef struct
{
	unsigned char       ucType; //定焦1 变焦2
	unsigned char       ucReserved[3];
}T_AssCameraType;

#ifndef _T_RCVMSG_
#define _T_RCVMSG_
typedef struct
{
	unsigned int		uiFlag;								/*标志位，111表示Version、IP、MAC*/
	unsigned char		aucDstMACAdd[6];					/*目标MAC地址*/
	char				aucAdapterName[VERSION_NAME_LEN];	/*网络适配器名称*/		
	unsigned int		uiAdapterSubMask;					/*网络适配器子网掩码*/
	char				ancDevType[64];						/* 设备类型，出厂时设定；*/
	char				ancSerialNum[64];					/* 设备序列号*/
	char				ancAppVersion[VERSION_NAME_LEN];	/* 软件版本*/
	char				ancDSPVersion[VERSION_NAME_LEN];	/* DSP版本*/
	T_NetSetup			tNetSetup;							/* 网络信息*/
	T_MACSetup			tMacSetup;							/* MAC信息*/
	//char		szHardwareVersion[VERSION_NAME_LEN];		/*硬件版本*/
}T_RcvMsg;
#endif

typedef struct 
{ 
	unsigned char ucRegState; /*0:注销 1：注册*/ 
	unsigned char aucReserved[31]; 
}T_RegState;//注册注销岗亭端

typedef enum 
{ 
	INPUT_INDEX_UNKNOW = 0, 
	INPUT_INDEX1, 
	INPUT_INDEX2, 
	INPUT_INDEX3, 
	INPUT_INDEX_MAX, 
}E_InputIndex; 

typedef enum 
{ 
	OUTPUT_INDEX_UNKNOW = 0, 
	OUTPUT_INDEX1, 
	OUTPUT_INDEX2, 
	OUTPUT_INDEX3, 
	OUTPUT_INDEX_MAX, 
}E_OutputIndex; 

typedef struct 
{ 
	unsigned char ucIndex; //E_InputIndex 
	unsigned char aucReserved[3]; 
}T_InputReadReq; 

typedef struct 
{ 
	unsigned char ucIndex; //E_InputIndex 
	unsigned char ucValue; //0,1 
	unsigned char ucState;//0表示成功
	unsigned char aucReserved[2]; 
}T_InputReadRsp; 

typedef struct 
{ 
	unsigned char ucIndex; //E_OutputIndex 
	unsigned char ucValue; //0,1 
	unsigned char aucReserved[2]; 
}T_OutputWriteReq;

typedef struct 
{ 
	unsigned int uiDataLen; 
	unsigned char aucDataBuff[256]; 
}T_TwoEncpyption;

typedef struct
{
	unsigned char	switchflag;// 1 打开  0 关闭 
	unsigned char	aucReserved[3];
	T_TwoEncpyption Encpyptioninfo;// 二次加密字符串
}T_TwoEncpyptionSet;//设置开启关闭

typedef struct
{
	T_TwoEncpyption Encpyptioninfo;// 二次加密字符串
	unsigned char	aucReserved[4];
}T_TwoEncpyptionAuth;//鉴权

typedef struct
{
	T_TwoEncpyption currentEncpyption;// 当前二次加密字符串
	T_TwoEncpyption newEncpyption;// 新二次加密字符串
	unsigned char	aucReserved[4];
}T_TwoEncpyptionModify;//修改

typedef struct
{
	unsigned char	switchflag;// 1 打开  0 关闭 
	unsigned char	aucReserved[3];
}T_TwoEncpyptionQuery;//查询开启关闭

typedef struct
{
	char acOldPwd[32]; /*AES 128位算法 加密MAC地址字符串,再base64*/
	T_TwoEncpyption Encpyptioninfo;// 二次加密字符串
}T_ResetTwoEncpyption;

typedef enum 
{ 
	LENS_TYPE_ZOOM_MANU = 0, 
	LENS_TYPE_ZOOM_AUTO_START, 
	LENS_TYPE_ZOOM_AUTO_STOP, 
	LENS_TYPE_FOCUS_MANU, 
	LENS_TYPE_FOCUS_AUTO_START, 
	LENS_TYPE_FOCUS_AUTO_STOP, 
	LENS_TYPE_MAX, 
}E_LensType; 

typedef enum 
{ 
	LENS_ACTION_SUBTRACT = 0, 
	LENS_ACTION_ADD, 
	LENS_ACTION_MAX, 
}E_LensAction; 

typedef struct 
{ 
	unsigned char	ucLensType; //E_LensType 
	unsigned char	ucLensAction; //E_LensAction 
	unsigned short usLensSteps; // 步数(1-20) 
}T_LensControl; 
typedef enum
{
	LIGHT_WORK_MODE_CLOSE = 0,
	LIGHT_WORK_MODE_OPEN,
	LIGHT_WORK_MODE_AUTO,
	LIGHT_WORK_MODE_ENERYGYSAVING,
	LIGHT_WORK_MAX
}E_LightWorkMode;
typedef enum
{
	PARK_LED_LEVEL_OFF = 0,
	PARK_LED_LEVEL1,
	PARK_LED_LEVEL2,
	PARK_LED_LEVEL3,
	PARK_LED_LEVEL4,
	PARK_LED_LEVEL5,
	PARK_LED_LEVEL6,
	PARK_LED_LEVEL7,
	PARK_LED_LEVEL_MAX,
}E_ParkLedLevel;
typedef struct
{
	unsigned char	ucWorkMode;// E_LightWorkMode
	unsigned char	ucLevel;		//E_ParkLedLevel
	unsigned char	ucLumaTH; //亮度阀值1~100 
	unsigned char	ucEnergySavingTimeOut;//多少分钟无车进入节能模式
}T_ParkLedLightSetup;
typedef struct 
{ 
	char acUserName[32]; 
	char acPasswd[36]; /*明文*/ 
}T_UserAccount; 
typedef struct
{
	char acOldUserName[32];
	char acOldPasswd[36];     /*明文*/
	char acNewUserName[32];
	char acNewPasswd[36];     /*明文*/
}T_ModifyUserAccount;
typedef struct 
{ 
	unsigned short	usUserPort;
	unsigned short	usReserved;
}T_UserPort; 
typedef enum 
{ 
	WL_FM_FULL = 0,	 /*精确比配*/ 
	WL_FM_SIMILAR = 0x1,	/*相似字符比配:0-D 8-B 0-Q E-F*/ 
	WL_FM_ORD_CHAR = 0x2, /*普通字符，允许错误失败个数*/ 
	WL_FM_IGN_CC = 0x4,	/*忽略汉字*/ 
	WL_FM_MAX, 
}E_WhilteListFuzzyMatch; 
/******************************************************************************************************
ucMatchMode 由三位决定
ucMatchMode	WL_FM_IGN_CC  WL_FM_ORD_CHAR  WL_FM_SIMILAR
	0			0				0				0			精确匹配模式
	1			0				0				1			相似字符匹配模式
	2			0				1				0			普通字符匹配模式
	3			0				1				1			相似字符匹配模式+普通字符匹配模式
	4			1				0				0			忽略汉字模式
	5			1				0				1			忽略汉字模式+相似字符匹配模式
	6			1				1				0			忽略汉字模式+普通字符匹配模式
	7			1				1				1			忽略汉字模式+普通字符匹配模式+相似字符匹配模式
*********************************************************************************************************/	
typedef struct 
{ 
	unsigned char	ucMatchMode; /*E_WhilteListFuzzyMatch*/ 
	unsigned char	ucValue; /*WL_FM_ORD_CHAR 时使用*/ 
	unsigned char	aucReserved[2]; 
}T_WLFuzzyMatch;

typedef enum 
{ 
	OP_MODE_UNKNOW = 0, 
	OP_MODE_OFFLINE,	 /*脱机使能*/ 
	OP_MODE_ENABLE,	 /*使能，不分区联机、脱机*/ 
	OP_MODE_DISABLE,	 /*不使能*/ 
	OP_MODE_MAX 
}E_OffLinePayMode; 

typedef struct
{
	unsigned char	ucMode;//E_OffLinePayMode
	unsigned char	aucReserved[3];
}T_OffLinePayMode;//脱机收费模式
typedef enum
{
	PARK_VEH_SIZE_UNKNOW = 0,
	PARK_VEH_SIZE_SMALL,
	PARK_VEH_SIZE_LARGE,
	PARK_VEH_SIZE_MAX
}E_ParkVehSize;

typedef enum
{
	PAY_MODE_UNKNOW = 0,
	PAY_MODE_ONTIME,/*按时计费 */
	PAY_MODE_TIMES,/*按次计费 */
	PAY_MODE_TIME_SECTION,/*分段计费 */
	PAY_MODE_TABLE,/*查表计费 */
	PAY_MODE_MAX
}E_PayMode;   /*计费模式*/

typedef enum
{
	STRATEGY_TYPE_UNKNOW = 0,
	STRATEGY_TYPE_NOPAY, //不收费
	STRATEGY_TYPE_CYCLE,//按一个周期收费
	STRATEGY_TYPE_BYTIME,//根据时长收费
	STRATEGY_TYPE_MAX
}E_StrategyType;  /*不足一个周期的计费策略*/
typedef struct
{
	unsigned char	ucEnable;
	unsigned char	ucVehType;	/*车辆类型*/
	unsigned char	aucReserved[2];
	unsigned short	usCyclePay;/* 周期收费金额*/
	unsigned short	usStartPay;/* 起步金额*/
	unsigned short	usFreeTime;/* 免费时长*/
	unsigned short	usCycleTime;/* 计费周期*/
	unsigned short	usStartTime;/* 起步时长*/
	unsigned short	usTotalPreDay;/* 封顶金额*/
}T_OnTimePay;  /*按时收费*/

typedef struct
{
	unsigned char	ucEnable;
	unsigned char	ucVehType;	/*车辆类型*/
	unsigned char	ucMaxTime;/*封顶次数*/
	unsigned char	ucReserved;
	unsigned short	usPayOne;/*一次收费金额*/
	unsigned short	usFreeTime;/*免费时长*/
	unsigned short	usFreeStartTime;  /*免费开始时间，以分钟为单位*/
	unsigned short	usFreeEndTime; /*免费结束时间，以分钟为单位*/
	unsigned short	usPayStartTime;  /*收费开始时间，以分钟为单位*/
	unsigned short	usPayEndTime;/*收费结束时间，以分钟为单位*/
}T_TimesPay; /*按次收费*/

typedef struct
{
	unsigned char	ucEnable;
	unsigned char	ucVehType;	/*车辆类型*/
	unsigned char	aucReserved[2];
	unsigned short	usCyclePay;/* 周期收费金额*/
	unsigned short	usStartPay;/* 起步金额*/
	unsigned short	usFreeTime;/* 免费时长*/
	unsigned short	usCycleTime;/* 计费周期*/
	unsigned short	usStartTime;/* 起步时长*/
	unsigned short	usTotalPreDay;/* 时段封顶金额*/
	unsigned short	usSectionStartTime;  /*时段开始时间，以分钟为单位*/
	unsigned short	usSectionEndTime;/*时段结束时间，以分钟为单位*/
}T_TimeSectionPay;	/*按时段收费*/

typedef struct
{
	unsigned short usFreeTime;
	unsigned short usTotalPreDay;
	unsigned short usTablePay[48];	
	unsigned char  ucTableType;  /* 0以半小时为单位,1以1小时为单位*/
	unsigned char aucReserved[3];
}T_TablePay; /*查表收费*/

typedef struct
{
	unsigned char	ucRuleMode; 		  /*E_PayMode*/
	unsigned char	ucStrategyType;    /*E_StrategyType*/
	unsigned short	usLimitTime;
	T_OnTimePay atOnTimePay[MAX_PAY_ITEM];
	T_TimesPay	  atTimesPay[MAX_PAY_ITEM];
	T_TimeSectionPay atTimeSectionPay[MAX_PAY_ITEM*MAX_TIMESECTION_NUM];
	T_TablePay atTablePay;
	unsigned char aucReserved[4];
}T_PayRule;

typedef struct
{
	unsigned char ucType;  /*导出信息内容，0为车辆在场信息表*/
	char aucLplPath[256];
}T_GetPrensentVehInfo;

typedef struct
{
	unsigned char	ucEntryEnable;//入口相机是否抬闸使能标志
	unsigned char	ucExitEnable;//入口相机是否抬闸使能标志
	unsigned char	aucReserved[2];
}T_AutoControlGate;

typedef enum
{
	Sync_OffLine_Pay_Rule,//同步收费规则
	Sync_OffLine_Pay_Mode,//同步收费模式
	Sync_OffLine_Auto_Open_Gate,//同步相机抬闸配置
	Sync_485Ctrl_Rule,//同步485规则
	Sync_LampCtrl_Rule,//同步灯控规则
	Sync_Max_Type
}E_SyncType;

typedef struct
{
	unsigned char	ucSyncType;//E_SyncType
	unsigned char	aucReserved[3];
}T_SyncConfigByMuticast;

typedef enum
{
	BlackWhiteList_NoError = 0, //正常
	BlackWhiteList_InvalidParam,//车牌信息格式不对
	BlackWhiteList_PlateLengthError,//车牌号码字符串长度不对
	BlackWhiteList_PlateInvalidCharError,//车牌号码包含无效字符
	BlackWhiteList_StartTimeLengthError,//开始时间字符串长度不对
	BlackWhiteList_StartTimeInvalidCharError,//开始时间字符串包含无效字符
	BlackWhiteList_StartTimeYearError,  //开始时间年份不对
	BlackWhiteList_StartTimeMonthError, //开始时间月份不对
	BlackWhiteList_StartTimeDayError,   //开始时间日期不对
	BlackWhiteList_StartTimeHourError,  //开始时间小时不对
	BlackWhiteList_StartTimeMinuteError,//开始时间分钟不对
	BlackWhiteList_StartTimeSecondError,//开始时间秒数不对
	BlackWhiteList_EndTimeLengthError,  //结束时间字符串长度不对
	BlackWhiteList_EndTimeInvalidCharError,//结束时间字符串包含无效字符
	BlackWhiteList_EndTimeYearError,    //结束时间年份不对
	BlackWhiteList_EndTimeMonthError,	//结束时间月份不对
	BlackWhiteList_EndTimeDayError,		//结束时间日期不对
	BlackWhiteList_EndTimeHourError,	//结束时间小时不对
	BlackWhiteList_EndTimeMinuteError,	//结束时间分钟不对
	BlackWhiteList_EndTimeSecondError,  //结束时间秒数不对
	BlackWhiteList_StartTimeHourBigEndTime,//开始时间大于结束时间
	BlackWhiteList_FormatError,//格式不正确
	BlackWhiteList_AccoundFormatError,//账号包含非数字字符
	BlackWhiteList_AccoundValueTooBig,//账号值太大
	BlackWhiteList_TotalNumFormatError,//总车位数包含非数字字符
	BlackWhiteList_TotalNumValueTooBig,//总车位数值不能大于255
	BlackWhiteList_IdleNumFormatError,//剩余车位数包含非数字字符
	BlackWhiteList_IdleNumValueBigTotalNum,//剩余车位数不能大于总车位数
	BlackWhiteList_IdleNumValueTooBig,//剩余车位数值不能大于255
	BlackWhiteList_SectionLengthError,//24小时时段格式长度必须为4
	BlackWhiteList_SectionFormatError,//24小时时段格式只能包含字符0-9,A-F
	BlackWhiteList_UTF8TransToUnicodeFormatError,//UTF8转Unicode错误
	BlackWhiteList_UnicodeTransToGBKFormatError,//UTF8转Unicode错误
}E_BlackWhiteListErrorCode;

typedef enum
{
	LOOP_IO_ID = 0, /* 线圈IO Id*/
	IO_INDEX_MAX,
}E_IOAppIndex;

typedef struct
{
	unsigned char	ucIndex; /* E_IOAppIndex*/
	unsigned char	ucLState; /* 0 下降沿跳变  1 上升沿跳变*/
	unsigned char	aucReserved[2];
}T_IOStateRsp;


typedef enum
{
	DEV_STATE_LED = 103, //状态灯
	NET_STATE_LED = 92, //网络灯
	VEH_CHECK_IN1 = 111, // 车检器输入1
	VEH_CHECK_IN2 = 104, // 车检器输入2
	VEH_CHECK_IN3 = 112, // 车检器输入3
	RELAY_OUT1 = 94, // 继电器输出1
	RELAY_OUT2 = 95, // 继电器输出2
	RELAY_OUT3 = 118, // 继电器输出3
	PARKING_SPACE_LED1_R = 33, // 车位相机LED1-R
	PARKING_SPACE_LED1_G = 32, // 车位相机LED1-G
	PARKING_SPACE_LED1_B = 11, // 车位相机LED1-B

	PARKING_SPACE_LED2_R = 13, // 车位相机LED2-R
	PARKING_SPACE_LED2_G = 10, // 车位相机LED2-G
	PARKING_SPACE_LED2_B = 12, // 车位相机LED2-B

	PARKING_SPACE_LED3_R = 14, // 车位相机LED3-R
	PARKING_SPACE_LED3_G = 15, // 车位相机LED3-G
	PARKING_SPACE_LED3_B = 9, // 车位相机LED3-B
}E_GPIOIndex;

typedef enum
{
	OFFLINE_DATA=0,
}E_OfflineDataType;

typedef struct
{
	unsigned char	ucType; /*E_OfflineDataType */
	unsigned char	aucReserved[3];
}T_ClearOfflineData;

typedef struct
{
	char	acPlate[16];	 /* 车牌号码，GB2312编码 */
	char	acEntryTime[18]; /* 入场时间*/
	char	acExitTime[18]; /* 出场时间*/
	unsigned int	uiRequired;  /* 应付金额，0.1元为单位*/
	unsigned int	uiPrepaid;  	/* 已付金额，0.1元为单位*/
	unsigned char 	ucVehState;   /*E_VehState*/
	unsigned char	ucVehType;  /* 车辆类型1小车2大车 */
	unsigned char	ucUserType;  /*会员类型E_MemberType*/
	unsigned char	ucPlateColor; /*车牌颜色，若为0，表示无效E_PlateColor*/
}T_OfflineVehInfoTest;

typedef struct
{
	unsigned char enable;		//0 关闭  1 开启语音对讲  2 播放音频   3 语音采集	4 拒绝对讲
	unsigned char pressstatus;	//0 未按下    1 有按下
	unsigned char ucOutTime;	//连接超时等等时间【3，30】 单位/秒
	unsigned char Reserverd[5];
}T_AudioTalkBack;

typedef struct
{
	unsigned char inVol;//输入音量大小 0-100
	unsigned char outVol;//输出音量大小 0-100
	unsigned char intype;//0 拾音器  1 麦克风
	unsigned char Reserverd[5];
}T_AudioVol;  //播报音量

typedef struct
{
	unsigned char avAudioVol; //音量大小 0-100
	unsigned char Reserverd[127];	
}T_AvAudioVol;	//媒体音量结构体


typedef enum
{
	TALK_CONN_STATE_UNKNOW = 0, 
	TALK_CONN_STATE_SUCC,			/*连接成功*/
	TALK_CONN_STATE_DIS,			/*连接中断*/
	TALK_CONN_STATE_ALL,
}E_TalkConnState;

typedef struct
{
	int iIpAddr;//IP地址
	unsigned char ucStatus;//状态  0  空闲  1  有连接
	unsigned char ucRerserved[127];
}T_AudioLinkInfo;

typedef enum 
{
	ROTATE_NONE = 0,
	ROTATE_90   = 1,
	ROTATE_180  = 2,
	ROTATE_270  = 3,
	ROTATE_BUTT
} E_ROTATE;


typedef struct
{
	unsigned char   ucRotateType; // E_ROTATE
	unsigned char	ucReserved[3]; 
}T_VideoRotate;


//////////////////////////////////////////////////////////////////////////

/*特征码结构体定义*/
typedef struct 
{
	char   strSpecialCode[20][12]; 
}T_SpecialCode;


/*图片信息结构体定义*/
typedef struct 
{
	unsigned short 	usWidth;   /*图片的宽度，单位:像素*/
	unsigned short	usHeight;  /*图片的高度，单位:像素*/

	T_Point		 atPlateRegion[4];    /*车牌识别区域，逆时针方向4个点*/
	unsigned short	usPlateBox[4];    /*车牌位置，左上角(0, 1), 右下角(2,3)*/
	unsigned short	usVehicleBox[4];  /*车身位置，左上角(0, 1), 右下角(2,3)*/

	char	strVehicleBrand[128]; /*车型*/
	char	strConfidence[12];    /*车型可信度*/

	T_SpecialCode   tSpecialCode;/*特征码*/

	int hasCar;				//是否有车

	unsigned char   ucReserved[256];  /*保留字段*/ 

}T_SpecialCodeImageInfo;

/*伪车牌图片信息结构体定义*/
typedef struct 
{
	unsigned short 	usWidth;   /*图片的宽度，单位:像素*/
	unsigned short	usHeight;  /*图片的高度，单位:像素*/

	unsigned short	usPlateBox[4];  /*车牌位置，左上角(0, 1), 右下角(2,3)*/
	unsigned short	usVehicleBox[4];  /*车身位置，左上角(0, 1), 右下角(2,3)*/

	char strVehicleSubBrand[128];	/*伪车牌*/
	char strConfidence[12];         /*伪车牌可信度*/

	unsigned char   ucReserved[256];  /*保留字段*/ 

}T_PlateClassfyImageInfo;

//上报主辅告警信息
typedef enum
{
	WARN_ASSIST_IP_FAILED=0,
}E_WarnInfoType;


typedef struct
{
	unsigned char   ucType;    // E_WarnInfoType
	unsigned char   ucReserved[3];
	unsigned char   szContent[128];//告警内容
}T_WarningInfo;

typedef struct
{
	unsigned char	ucEnable;  // 远程调试功能是否开启
	unsigned char	hb_interval;//心跳间隔   单位S
	unsigned char	ucPlatePush; // 是否推送车牌识别结果0 否  1 是
	unsigned char	ucBigPic;  //  发送图片
	unsigned char	ucSmallPic; //  发送小图
	unsigned char	ucVideoflag;//视频开关
	unsigned char	msg_timeout;
	unsigned char	ucLogFlag;	//日志开关
	unsigned char	uaReserved[2];
	unsigned short  cloudport;//远程服务端口号
	char 			cloudaddr[64];//远程服务地址,可支持IP地址和域名，如 192.168.1.199或者www.baidu.com
	unsigned char	uaReserved2[128];
}T_CloudParam;

typedef struct
{
	unsigned char	ucIOType; // 0: 查询输入 1:查询输出
	unsigned char	ucIndex; //E_InputIndex/E_OutputIndex
	unsigned char	ucValue;  //0,1
	unsigned char	ucState;  //相机读取IO状态 0:成功 非0:失败
	unsigned char	ucReserved[8];
}T_QueryIOState;


typedef struct
{
	char			szLpr[16];			//车牌号
	unsigned short  uwMLpBox[4]; // 主车牌位置
	unsigned short	uwVLpBox[4]; // 辅车牌位置
	unsigned int	uiLprWidth;         //  车牌宽度
	unsigned char   ucLpColor;          //车牌颜色
	unsigned char   ucReal;             // 0 假车牌 1 真车牌
	unsigned char   ucLprType;			// 0 标定车牌1 测试车牌
	unsigned char   ucEnable;
	unsigned char   ucReserved[12];
}T_GoalPlateInfo;

typedef struct
{
	T_GoalPlateInfo tGoalPlateInfo[8];
	unsigned int uiPlateNum;  // 车牌数
}T_CamCheckInfo;

typedef enum
{
	CAM_CHECK_NO_ERROR				= 0,  //成功
	CAM_CHECK_NO_FOUND_G			= 1, // 没有找到标定车牌
	CAM_CHECK_NO_FOUND_T			= 2, // 没有找到测试车牌
	CAM_CHECK_TRUE_TO_FALSE			= 3, // 真车牌识别为假车牌
	CAM_CHECK_FALSE_TO_TRUE			= 4,  // 假车牌识别为真车牌
	CAM_CHECK_INVALID_WIDTH_G		= 5,  // 标定车牌宽度异常
	CAM_CHECK_INVALID_WIDTH_T		= 6,  // 测试车牌宽度异常
	CAM_CHECK_PLATE_NUM				= 7,  //车牌数量不足
	CAM_CHECK_API_ERROR				= 8,  //标定接口调用失败
	CAM_CHECK_INVALID_PARAM			= 9, // 参数其他错误
}E_CAM_CHECK_CODE;

typedef struct
{
	T_GoalPlateInfo tGoalPlateInfo[8];
	unsigned int uiPlateNum;  // 车牌数
	unsigned char  ucResultCode;    // E_CAM_CHECK_CODE
	unsigned char  ucReserved[3];
}T_CamCheckResult;

typedef struct
{
	unsigned char	type;//连接外网类型 0 : 走4G   1:走有线
	unsigned char	uaReserved[63];
}T_Wired4GSet;

typedef struct
{
	unsigned char	ucState;//1 开启队列模式 2 关闭队列模式
	unsigned char	ucIndex;
	unsigned char	ucReserved[2];  

}T_ControlGateQueue;

typedef enum
{
	CHARGE_DEFAULT= 0,
	CHARGE_TIMES,		
	CHARGE_DAYNIGTH,		
	CHARGE_SETTING,		
	CHARGE_MAX,
}E_CHARGE_TYPES;

//收费结构联合体
typedef union 
{	
	struct//标准收费
	{		    
		unsigned short ChargeTag;      	//是否收费有效标识
		unsigned short FreeMin;	//免费分钟
		unsigned short ChargeByte[24];	//停车时长1 - 24小时的收费金额
		unsigned short DayMaxCharge;  //最高收费金额
		unsigned short Freeflag;           //免费时间是否计费
		unsigned short Reserve3;
		unsigned short ChargeType;     //收费类型
		unsigned short Reserve6[2];    //空保留使用
	}Default_Charge;

	struct//按次收费
	{
		unsigned short ChargeTag;      //是否收费有效标识
		unsigned short FreeMin;	//免费分钟
		unsigned short TimeCharge;     //按次收费金额
		unsigned short ChargeByte[23]; //空
		unsigned short DayMaxCharge; //最高收费金额
		unsigned short Freeflag;       //免费时间是否计费
		unsigned short Reserve3;
		unsigned short ChargeType;     //收费类型
		unsigned short Reserve6[2];    //空保留使用
	}Times_Charge;		

	struct//白天晚上收费
	{
		unsigned short ChargeTag;      //是否收费有效标识
		unsigned short FreeMin;        //免费分钟   
		unsigned short StartHour;      //白天时段起始小时
		unsigned short StartMin;       //白天时段起始分钟
		unsigned short EndHour;        //白天时段结束小时
		unsigned short EndMin;         //白天时段结束分钟
		unsigned short Reserve1;       //空保留使用
		unsigned short DayUnit;        //白天计时单位
		unsigned short DayCharge;	   //白天每计时单位收费额
		unsigned short Reserve2;       //空保留使用
		unsigned short NightUnit;	   //晚间计时单位
		unsigned short NightCharge;    //晚间每计时单位收费额
		unsigned short DayOneMaxCharge;       //白天最高收费额
		unsigned short NightOneMaxCharge;     //晚间最高收费额
		unsigned short Reserve4[2];        //保留
		unsigned short DayFirstUnit;   //白天首计时收费
		unsigned short NightFirstUnit; //晚间首计时收费
		unsigned short DayFirstHour;   //白天首计时小时
		unsigned short DayFirstMin;    //白天首计时分钟
		unsigned short NightFirstHour; //晚间首计时小时
		unsigned short NightFirstMin;  //晚间首计时分钟
		unsigned short Reserve5[4];    //空保留使用
		unsigned short DayMaxCharge; //最高收费金额
		unsigned short Freeflag;       //免费时间是否计费
		unsigned short Reserve7;
		unsigned short ChargeType;     //收费类型
		unsigned short Reserve8;    //空保留使用
		unsigned short FirstFlag;      //首计时处理标志	
	}Day_NightCharge;

	struct	//按设定时间收费
	{
		unsigned short ChargeTag;       //是否收费有效标识
		unsigned short FreeMin;	//免费分钟
		unsigned short Reserve1[5];     //空保留使用
		unsigned short DayUnit;         //计时单位
		unsigned short DayCharge;	    //每计时单位收费额
		unsigned short Reserve2[7];     //空保留使用
		unsigned short DayFirstUnit;    //首计时收费
		unsigned short Reserve3;     //空保留使用
		unsigned short DayFirstHour;    //首计时小时
		unsigned short DayFirstMin;     //首计时分钟
		unsigned short Reserve4[6];     //空保留使用
		unsigned short DayMaxCharge; //最高收费金额
		unsigned short Freeflag;        //免费时间是否计费   
		unsigned short PointMoney;      //过零点收费金额
		unsigned short ChargeType;      //收费类型
		unsigned short Reserve6;     //空保留使用
		unsigned short FirstFlag;       //首计时处理标志	
	}SetTime_Charge;
}CHARGE_UNION;			  				  

typedef struct
{
	unsigned char		ucIndex;  // 0:小车收费规则   1:大车收费规则
	unsigned char		uaReserved[3];
	CHARGE_UNION		chargeparam;
	unsigned char		uaReserved2[256];
}T_CHARGE_PARAM_FRTK;

#define MAX_LCD_LINES	8
#define MAX_LCD_DISPALY_LINE 8
typedef enum
{
	BIT_LCD_VEH_PLATE =		0x01,/*车牌显示*/
	BIT_LCD_VEH_LEFT =		0x02,/*剩余停车位显示*/
	BIT_LCD_INTIME =		0x04,/*入场时间显示*/
	BIT_LCD_OUTTIME =		0x08,/*出场时间显示*/
	BIT_LCD_VEH_PAY =		0x10,  /*停车付费显示*/
	BIT_LCD_VEH_TIME =		0x20, /*停车时间显示*/
	BIT_LCD_VEH_USERTYPE =	0x40,  /*停车用户类型*/
	BIT_LCD_VEH_PERIOD =	0x80, /*月租有效期显示*/
	BIT_LCD_CUSTOM =		0x100,  /*自定义内容显示*/
	BIT_LCD_LOCALTIME =		0x200,  /*显示系统时间*/
	BIT_LCD_MAX,
}E_LCdModeBit;

typedef enum
{
	FONT_BLACK = 0,//黑色
	FONT_RED,//红色
	FONT_BLUE,//蓝色
}E_LCdFontColor;

typedef struct
{
	unsigned short		uaBox[4];//坐标位置
	unsigned char		ucEnable;//使能
	unsigned char		ucsize;//字体大小 0大  1中 2小 E_LCDFontSize
	unsigned char		uccolor;//字体颜色E_LCdFontColor
	unsigned char		ucaudioEnable;//语音播放使能
	unsigned int  		usModeBit;	//E_LCdModeBit
	char				acContent[56]; //GB2312，自定义模式有效
	unsigned char  		ucReserved[12];
}T_LCdLineSetup;//注意，该结构体不能超过70直接(一个消息包超过1400)

typedef struct
{
	unsigned char   ucLcdid;					//LCD屏显协议号
	unsigned char   ucLcdScreenMode;			//E_LedScreenMode
	unsigned short	usBrightnessTH;             /* 亮度阀值 1~100*/
	unsigned char	ucCtlMode;					//亮度控制模式 0自动 1手动
	unsigned char   ucFontRollSpeed;          //文字滚动速度 E_LCDFontRollingSpeed
	unsigned char   ucAudioPlaySpeed;         //语音播报速度 E_LCDAudioSpeed
	unsigned char	uaReserved[121];
}T_LcdShowSetup;

typedef struct
{
	T_LCdLineSetup   atSubLcdIdle[MAX_LCD_LINES];//出口或者入口 空闲
	T_LCdLineSetup   atSubLcdBusy[MAX_LCD_LINES];//出口或者入口 忙  
	unsigned char			 uaReserved[32];
}T_SLCdSetup;

typedef struct
{
	unsigned short		uaBox[4];//坐标位置
	unsigned char		uchidden;//隐藏  0:否  1:是
	unsigned char		ucsize;//字体大小
	unsigned char		uccolor;//字体颜色E_LCdFontColor
	unsigned char		ucReserved;
	char		acContent[80]; //显示内容,GB2312编码
	unsigned char  		uaReserved[16];
}T_Linecontent;

typedef struct
{
	T_Linecontent line[MAX_LCD_DISPALY_LINE];//0-7行LCD屏显内容配置
	char		  BpicName[64];//背景图片路径
	unsigned char  		  ucId;//编号
	unsigned char  		  uaReserved[63];
}T_DisplayContent;//内容显示

typedef struct
{
	unsigned char  		  ucId;//编号
	unsigned char		  invisible;// 1:可见  0:不可见(用于播放视频)
	unsigned char  		  uaReserved[126];
	char		  picturePath[64];//图片路径,当路径名同上次不一致时，就刷新
}T_ADShowSet;//广告区域配置

//LCD 广告文件播放设置
typedef enum
{
	QY_AD_VIDEO=0,// 广告视频
	QY_AD_PICTURES,// 广告图片
	QY_BG_IDLE_PICTURES,//闲时背景图片
	QY_BG_BUSY_PICTURES,//忙时背景图片
	QY_QRCODE_PICTURES,//收费二维码图片
	QY_PLAY_MAX,
}E_AdvertisingType;

typedef struct
{
	unsigned char 	ucEnable;//播放使能
	unsigned short	ucIndex;//播放序号
	unsigned char 	uctype;//文件属性 E_AdvertisingType
	unsigned short	uctimes;//文件为视频时，用到该字段,播放次数
	unsigned short	ucstaytime;//文件为图片时，用到该字段,停留时长  单位S
	char 	aName[56];//文件名
	unsigned char	uaReserved[20];
}T_AD_fileinfo;//注意，该结构体不能超过70直接(一个消息包超过1400)

#define MAX_AD_UPLINES	16
#define MAX_AD_DOWNLINES 8

typedef struct
{
	T_AD_fileinfo   downAdIdle[MAX_AD_DOWNLINES];//出口或者入口 空闲
	T_AD_fileinfo   downAdBusy[MAX_AD_DOWNLINES];//出口或者入口 忙  
	unsigned char			uaReserved[16];
}T_DADSetup;//下区广告

typedef struct
{
	T_AD_fileinfo   upAdInfo[MAX_AD_UPLINES];//上区广告
	unsigned char			 uaReserved[16];
}T_UADSetup;//上区广告

typedef struct
{
	unsigned char ucstatus;// 1:转码成功  0:未知
	unsigned char ucType;// 文件类型 0：视频  1图片
	unsigned char uaReserved[30];
}T_VideoUadIdle;


typedef struct
{
	T_VideoUadIdle vinfo[16];
	unsigned char uaReserved[256];
}T_VideoUADInfo;

typedef struct
{
	unsigned char ucLcdShowMode;	//E_LCDADShow
	unsigned char uaReserved[127]; //保留字段
}T_LcdShowMode;//显示模式

typedef enum
{
	LCD_AREA_HALF = 0,		//半屏
	LCD_AREA_FULL = 1,		//全屏
} E_LCDADShow;//LCD显示区域

typedef enum
{
	FONT_SIZE_MIN = 0,	//大
	FONT_SIZE_MED = 1,	//中
	FONT_SIZE_MAX = 2,	//小
}E_LCDFontSize;	//LCD字体大小

typedef enum
{
	FONT_SPEED_FAST   = 0,		//快速
	FONT_SPEED_MEDIUM = 1,		//中速
	FONT_SPEED_IDLING = 2,		//慢速	
} E_LCDFontRollingSpeed;//lcd字体滚动速度

typedef enum
{
	AUDIO_SPEED_FAST   = 0,		//快速
	AUDIO_SPEED_MEDIUM = 1,		//中速
	AUDIO_SPEED_IDLING = 2,		//慢速
} E_LCDAudioSpeed;//语音播放速度

typedef enum
{
	MIPI_2_LVDS_15=0,	 //mipi15寸
	MIPI_2_LVDS_18,		//mipi18寸
	MIPI_2_LVDS_21,		//mipi21寸
	MIPI_2_LVDS_MAX
} E_LCDScreenSize;	//屏幕尺寸

typedef struct
{
	unsigned char ucLcdScreenSize;	//E_LCDScreenSize
	unsigned char uaReserved[127];
}T_LcdScreenSize;//屏幕尺寸

/*配置摄像头参数时段*/
typedef struct
{
	unsigned  char 	ucEnable;    /*是否使能0:disable 1:enable*/
	unsigned  char  ucProfileId; /* 0:白天, 1:夜晚, 2:profile1, 3:profile2 */
	unsigned  char  aucReserve[2];
	unsigned  short usStartTime;  /*开始时间单位:分钟0~1440*/
	unsigned  short usEndTime;   /*结束时间单位:分钟0~1440*/
	unsigned  char  aucReserve2[32];
}T_PresetCameraTime;

/* 预置摄像头参数配置 */
typedef struct
{
	T_PresetCameraTime atItem[4]; /* 客户需要支持预置四个时段 */
	unsigned  char aucReserve[80];
}T_PresetCameraCfg; 
//实时显示信息下发
typedef struct
{
	unsigned char	fontcolor;	// 字体颜色 0:白  1:红   2:黑
	unsigned char	fontsize;	// 字体大小 0:大  1:中   2:小
	unsigned char	uaReserved[17];
	char	lcdcontent[80];//  显示内容,该内容为空时，该行不显示
}T_DInfoUnit;

typedef struct
{
	T_DInfoUnit line[5];// 1-5行显示内容配置
	unsigned char ucSecond;	// 自动切换时间单位:秒，0为不切换[0,255]
	unsigned char	uaReserved[255];
}T_LcdDInfoRtime;

//收费图片设置
typedef struct
{
	unsigned char	ucEnable;// 0 :隐藏   1:显示
	unsigned char	ucMode;// 0 :字符串(相机转成二维码图片)   1:url二维码图片地址
	char	uastr[255];
	unsigned char ucSecond;	// 自动切换时间单位:秒，0为不切换[0,255]
	char	uaReserved[255];
}T_LcdShowQRCode;

//实时语音播报
typedef enum
{
	lcd_plate_audio = 0x01,//车牌号播报
	lcd_charge_audio = 0x02,// 收费金额
	lcd_YLPA_audio = 0x04,// 播报"一路平安"
	lcd_HYGL_audio = 0x08,// 播报"欢迎光临"
	lcd_TTIME_audio = 0x010,// 停车时长
}E_LcdPaType;

typedef struct
{
	unsigned char	ucMode;// 0:固定语音模式  1:万能语音模式(暂时不支持)
	//当ucMode为0时，有效
	unsigned char	uaReserved[3];
	unsigned int	fee;//收费金额,单位角
	char	uPlate[16];//车牌号
	unsigned int	totaltime;//停车时长,单位分钟
	//当ucMode为1时，有效
	char	audiostr[128];// 万能语音播放内容 
	unsigned int	ucPlayMode;// E_Lcd_PaType  如: lcd_plate_audio | lcd_charge_audio | lcd_YLPA_audio
	char	uaReserved2[252];
}T_LcdRTAudioPlay;

typedef struct
{
	unsigned char   ucAdMode;  //1：切换闲时广告
	unsigned char	uaReserved[255];
}T_LcdAdAudioMode;

typedef enum
{
	FONT_ALIGN_LEFT = 0,			        //左对齐
	FONT_ALIGN_RIGHT = 1,			//右对齐
	FONT_ALIGN_CENTER = 2,			//居中对齐
} E_LCDFontAlgin;

typedef struct
{
	unsigned char font_align_mode;		//对齐方式 E_LCDFontAlgin
	unsigned char uaReserved[255];
} T_LcdFontAlign;

typedef enum
{
	LCD_ADVERT_VIDOE,
	LCD_ADVERT_IMAGE
}E_AdvertFile_Type;

typedef struct 
{
	E_AdvertFile_Type  eAdvertType;
	char szFileName[256];
}T_ExportAdvertFile;

/*设备经纬度*/
typedef struct
{
	float			fLongitude;			//经度[0-180]值包含小数点
	float			fLatitude;            //纬度[0-180]值包含小数点
	unsigned char	aucResreved[512];
}T_DevQuadrillage;

/*adtg格设备信息*/
typedef struct
{
	char			acDeviceSN[32];	//设备SN码
	char	        aucDeviceRegistCode[32];	//设备注册码
	unsigned int	uiProduceId;	//产品ID
	unsigned char	aucReserved[512];	
} T_AdtgDeviceParam;

/*指示灯配置信息*/
typedef struct
{
	unsigned char ucRiseLockFlag ;/*升锁标志 0关闭 1打开*/
	unsigned char ucDropLockFlag ;/*降锁标志 0关闭 1打开*/
	unsigned char  ucReserved[34]; /**预留34个字节*/
}T_LockIndicatorLight;

/*锁状态编码*/
typedef enum
{
	PARKING_STATE_UNKNOW,		//未知
	PARKING_STATE_CONNECT,		//连接正常
	PARKING_STATE_ERROR,		//连接异常
}E_Parking_StateCode;


/*单个车位配置信息*/
typedef struct
{
	unsigned char	bEnable;					/*该车位是否使能 0 不使能  1使能*/
	unsigned char	ucIndicatorLightNum;		//指示灯编号 对应下标
	char			ucParkingSpaceNum[16];		/*车位编号*/
	char			ucParkingSpaceLockNum[32];	/*车位锁编号*/
	char			acVersion[18];				//版本信息
	unsigned char	ucParkingState;				//地锁状态        //E_Parking_StateCode	
	unsigned char  ucReserved[111];
}T_LockParkingSpaceInfo;

/*识别区域的配置*/
typedef struct
{
	T_Point stPoint[4];
}T_LockIdentifyArea;


/*车位配置信息*/
typedef struct
{
	unsigned char   SnapFlag; /*抓拍标志 0全景抓拍 1局部抓拍*/
	T_LockIndicatorLight stIndicatorLight[3]; /*指示灯配置*/
	T_LockParkingSpaceInfo stParkingSpaceInfo[3];//车位配置配置 目前只用2个  预留一个车位
	unsigned char ucReserved[63]; /**预留63个字节*/
}T_LockParkingSpace;

//协议类型
typedef enum {
	PROTOCOL_TYPE_UNENABLE,	//未知
	PROTOCOL_TYPE_QYZN,		//(1)芊熠智能
	PROTOCOL_TYPE_DDCT,		//(2)钉钉车位锁
	PROTOCOL_TYPE_ATILA,	//(3)阿提拉车位锁
	PROTOCOL_TYPE_KELIMA,	//(4)克莱玛车位锁
	PROTOCOL_TYPE_MAX		//最大
}E_Lock_ProtocolType;

/*车位锁配置信息*/
typedef struct
{
	unsigned char	ucProtocolType;		/*协议标志(enLock_ProtocolType)*/
	unsigned char	ucParkingTime;		/*安全停车时间(最大255)*/
	unsigned char	ucBatteryWaring;	//电量预警值     [0-100]
	unsigned char	ucBatteryError;		//电量故障值	[0-100]
	unsigned int	uiSleepStartTime;	//休眠开始时间
	unsigned int	uiSleepEndTime;		//休眠结束时间
	unsigned char	ucSleepEnable;		//本地模式是否启用休眠 0 不启用 1启用
	unsigned char	ucReserved[119];		/*预留字节*/
}T_LockParkingSpaceLock;
//远程控制升降锁
typedef enum {
	REMOTE_CTRL_DOWN,//降下
	REMOTE_CTRL_UP,//升起
	REMOTE_CTRL_MAX
}E_LOCK_REMOTECTRL;

/*远程控制命令*/
typedef struct
{
	unsigned char ucRemoteCtrlCmd;/*远程控制升降锁的命令(E_LOCK_REMOTECTRL)*/
	unsigned char ucLockSeriarlNum; /*锁的编号(从1开始)*/           	            
	unsigned char  ucReserved[66];         /**预留62个字节*/
}T_LockRemoteCtrl;

typedef enum
{
	TRIGGER_TYPE_NEWENERGYCAR = 0x1,//新能源车
	TRIGGER_TYPE_FUELCAR = 0x2,		//燃油车
	TRIGGER_TYPE_MAX
}E_TRIGGER_TYPE;

/*触发控锁类型*/
typedef struct
{
	unsigned int	uiTriggerType;  /*触发控锁类型 详细见 E_TRIGGER_TYPE 多个组合按或*/
	unsigned char	ucReserved[24]; /**预留24个字节*/
}T_LockTriggerType;


typedef struct
{
	unsigned char ucIndex;  // 0 管理软件
	unsigned char ucState;   // 0 断开1 连接
	unsigned char aucReserved[62];    //保留位
}T_RemoteStateRsp;

typedef enum
{
	TEST_FLAG_STOP, /*灯控测试结束*/
	TEST_FLAG_START, /*灯控测试开始*/
	TEST_FLAG_MAX,
}E_TestFlag;

typedef struct
{
	unsigned char	ucTestFlag;  //E_TestFlag(默认是：TEST_FLAG_STOP)
	unsigned char	ucIntervalTime;//间隔时间(默认1(单位是：秒)(区间是1~255))
	unsigned char 	aucReserved[30];// 预留
}T_LampTest;

typedef enum
{
	HTTP_TOGETHER_UP = 0,		//一起上传
	HTTP_RESPECTIVELY_UP = 1	//分别上传
} E_HTTP_UP_MODE;

typedef struct
{
	unsigned char ucHttpUpMode; //上传模式 E_HTTP_UP_MODE
	unsigned char aucReserved[63];
}T_HttpUpImageMode;

typedef struct
{
	unsigned char lprListMode;				//删除黑白名单模式(0:白名单。1:黑名单 2:全部)
	unsigned char aucReserved[127];			//保留字段
}T_DeleteLprMode;//删除黑白名单类型

typedef enum 
{ 
	BL_MODE_DISABLE = 0,	 /*黑名单 不使能*/ 
	BL_MODE_ENABLE,			/*黑名单使能*/ 
	BL_MODE_MAX 
}E_BlackListMode; 

typedef struct
{
	unsigned char ucMode;//详见 E_BlackListMode
	unsigned char acReserved[31];
}T_BlackListMode;

//地锁IO输出状态
typedef enum
{
	IOOUT_NORMAL_OPEN,		//常开
	IOOUT_NORMAL_CLOSE,		//常闭
	IOOUT_NORMAL_MAX
}E_LockIoOutState;

typedef struct
{
	unsigned char	ucOutState;				//地锁输出状态 E_LockIoOutState
	unsigned char	ucIOIndex;				//0:输出1  1：输出2
	unsigned short	usOutTime;				//输出持续时间 [0,300]
	unsigned char	ucReserved[128];		//保留字段2
}T_LockIoOutInfo;

/*IO输出测试*/
typedef struct
{
	unsigned char ucIOIndex;			//0:输出1   1：输出2
	unsigned char ucReserved2[127];		//保留字段
}T_LockIoOutTestInfo;

/**********************************************************************
* 函数名称：Net_EnableLog
* 功能描述：日志功能开关,默认开启日志
* 输入参数：iEnable 0:关闭日志,1:启用日志
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_EnableLog(int iEnable);

NET_API E_ReturnCode _stdcall Net_Log(char *strLog, ...);

NET_API E_ReturnCode _stdcall Net_SetLogSize(int iSize);

/**********************************************************************
* 函数名称：Net_FindDevice
* 功能描述：搜索局域网内所有相机IP，通过注册回调函数获取所有相机信息,系统需要安装有WinPcap抓包工具
* 输入参数：无
* 输出参数：无
* 返 回 值：状态码  
***********************************************************************/
typedef void (CALLBACK *NET_FIND_DEVICE_CALLBACK)(T_RcvMsg *ptFindDevice, void *pUserData);
NET_API E_ReturnCode _stdcall Net_FindDevice(NET_FIND_DEVICE_CALLBACK func, void *pUserData);

NET_API E_ReturnCode _stdcall Net_FindDeviceEx(NET_FIND_DEVICE_CALLBACK func, void *pUserData);

/**********************************************************************
* 函数名称：Net_FindDeviceMac
* 功能描述：搜索局域网内所有相机Mac，通过注册回调函数获取所有相机Mac信息,系统需要安装有WinPcap抓包工具
* 输入参数：无
* 输出参数：无
* 返 回 值：状态码  
***********************************************************************/
typedef void (CALLBACK *NET_FIND_DEVICE_MAC_CALLBACK)(const char *strFindDeviceMac, void *pUserData);
NET_API E_ReturnCode _stdcall Net_FindDeviceMac(NET_FIND_DEVICE_MAC_CALLBACK func, void *pUserData);

/**********************************************************************
* 函数名称：Net_FindDeviceIp
* 功能描述：搜索局域网内所有相机Ip，通过注册回调函数获取所有相机Ip信息,系统需要安装有WinPcap抓包工具
* 输入参数：无
* 输出参数：无
* 返 回 值：状态码  
***********************************************************************/
typedef void (CALLBACK *NET_FIND_DEVICE_IP_CALLBACK)(const char *strFindDeviceIp, void *pUserData);
NET_API E_ReturnCode _stdcall Net_FindDeviceIp(NET_FIND_DEVICE_IP_CALLBACK func, void *pUserData);

/**********************************************************************
* 函数名称：Net_ModifyDeviceIpByMac
* 功能描述：根据相机Mac修改Ip,子网掩码
* 输入参数：strMac （必填）要修改的相机MAC地址	如 AB:66:33:55:00:78
			strIp	（必填）要修改成什么IP地址 如 192.168.1.199
			strMaskAddress（必填）掩码
* 输出参数：无
* 返 回 值：状态码  
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_ModifyDeviceIpByMac(const char *strMac, const char *strIp, const char *strMaskAddress);

/**********************************************************************
* 函数名称：Net_Init
* 功能描述：sdk库初始化，初始化相机管理资源
* 输入参数：无
* 输出参数：无
* 返 回 值：状态码  
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_Init(void);

/**********************************************************************
* 函数名称：Net_UNinit
* 功能描述：sdk库反初始化，断开相机连接，释放相机管理资源
* 输入参数：无
* 输出参数：无
* 返 回 值：无  
***********************************************************************/
NET_API void _stdcall Net_UNinit(void);

/**********************************************************************
* 函数名称：Net_AddCamera
* 功能描述：添加相机，分配相机管理项
* 输入参数：相机IP,"***.***.***.***"
* 输出参数：无
* 返 回 值：相机句柄,-1为无效句柄
***********************************************************************/
NET_API DCHANDLE _stdcall Net_AddCamera(char *ptIp);

/**********************************************************************
* 函数名称：Net_AddAssCamera
* 功能描述：添加辅相机，分配相机管理项
* 输入参数：ptIp 相机IP,"***.***.***.***"
			nAssDevFlag 辅相机设备标志
* 输出参数：无
* 返 回 值：相机句柄,-1为无效句柄
***********************************************************************/
NET_API DCHANDLE _stdcall Net_AddAssCamera(char *ptIp, int nAssDevFlag);

/**********************************************************************
* 函数名称：Net_DelCamera
* 功能描述：断开与相机之间的连接，释放相机管理项
* 输入参数： 相机句柄
* 输出参数： 无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_DelCamera(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_ConnCamera
* 功能描述：与相机建立控制信令，启动图片接收，第一次链接成功后，SDK内部机制自带断线重连机制，断线时候会不断重连
* 输入参数：tHandle 相机句柄
*           usPort  相机信令端口，为0时，使用默认端口30000
* 			usTimeout 信令处理超时时长，单位为秒
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_ConnCamera(DCHANDLE tHandle,  unsigned short usPort,  unsigned short usTimeout);

/**********************************************************************
* 函数名称：Net_ConnCameraEx
* 功能描述：Net_ConnCamera函数的扩展，与相机建立控制信令，启动图片接收,需要输入用户名和密码，第一次链接成功后，SDK内部机制自带断线重连机制，断线时候会不断重连
* 输入参数：tHandle 相机句柄
*           usPort  相机信令端口，为0时，使用默认端口30000
* 			usTimeout 信令处理超时时长，单位为秒
*			pUserName	用户名
*			pPassWord	密码
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_ConnCameraEx(DCHANDLE tHandle,  unsigned short usPort,  unsigned short usTimeout,unsigned char *pUserName,unsigned char *pPassWord);

NET_API E_ReturnCode _stdcall Net_ConnCameraEtcp(DCHANDLE tHandle,  unsigned short usPort, unsigned short usTimeout, unsigned char *pUserName,unsigned char *pPassWord, int ucDetectMode);
/**********************************************************************
* 函数名称：Net_DisConnCamera
* 功能描述：断开与相机之间的信令链路，释放图片接收资源
* 输入参数：相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_DisConnCamera(DCHANDLE tHandle);

/*********************************************************************
* 函数名称：Net_StartVideo
* 功能描述：开始接收视频码流，并将视频刷到窗口句柄上
* 输入参数：tHandle 相机句柄，
*				   niStreamType 流类型0表示主码流，1表示辅码流
*			hWnd 窗口句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_StartVideo(DCHANDLE tHandle, int niStreamType, HWND hWnd);

/**********************************************************************
* 函数名称：Net_SetRealDataCallBack
* 功能描述：注册码流接收函数，通过注册回调函数，获取实时视频帧
* 输入参数：tHandle 相机句柄
*			pRealDataCallBack 回调函数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef void (CALLBACK *NET_REALDATACALLBACK) (DCHANDLE tHandle, DWORD dwDataType, BYTE *pBuffer, DWORD dwBufSize, void* pUser);
NET_API E_ReturnCode _stdcall Net_SetRealDataCallBack(DCHANDLE tHandle, NET_REALDATACALLBACK pRealDataCallBack);

/**********************************************************************
* 函数名称：Net_SetRealDataCallBackEx
* 功能描述：注册码流接收函数，通过注册回调函数，获取实时视频帧，Net_SetRealDataCallBack函数的扩展，增加了回调函数上下文
* 输入参数：tHandle 相机句柄
*			pRealDataCallBack 回调函数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef void (CALLBACK *NET_REALDATACALLBACKEx) (DCHANDLE tHandle, DWORD dwDataType, BYTE *pBuffer, DWORD dwBufSize,T_FrameInfo *pTframeInfo, void* pUserData);
NET_API E_ReturnCode _stdcall Net_SetRealDataCallBackEx(DCHANDLE tHandle, NET_REALDATACALLBACKEx pRealDataCallBack,void *pUserData);

/**********************************************************************
* 函数名称：Net_AddPlayWindow
* 功能描述：添加播放视频的窗口句柄
* 输入参数：tHandle 相机句柄
*			hWnd	窗口句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_AddPlayWindow(DCHANDLE tHandle, HWND hWnd);

/**********************************************************************
* 函数名称：Net_DelPlayWindow
* 功能描述：删除播放视频的窗口句柄
* 输入参数：tHandle 相机句柄
*			hWnd	窗口句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_DelPlayWindow(DCHANDLE tHandle, HWND hWnd);

/**********************************************************************
* 函数名称：Net_SaveBmpFile
* 功能描述：保存当前帧为位图文件,图片路径所在盘不能小于2M，否则返回 DC_MEMORY_LACK 内存申请失败
* 输入参数：tHandle 相机句柄
*           strBmpFile 位图文件名
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_SaveBmpFile(DCHANDLE tHandle, const char * strBmpFile);

/**********************************************************************
* 函数名称：Net_SaveJpgFile
* 功能描述：保存当前帧为Jpg文件,图片路径所在盘不能小于2M，否则返回 DC_MEMORY_LACK 内存申请失败
* 输入参数：tHandle 相机句柄
*           strJpgFile 位图文件名
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_SaveJpgFile(DCHANDLE tHandle, const char * strJpgFile);

/**********************************************************************
* 函数名称：Net_GetJpgBuffer
* 功能描述：获取当前帧的Jpg缓存
* 输入参数：tHandle 相机句柄
*           ucJpgBuffer Jpg缓存指针, 内存由函数内部分配
* 输出参数：lSize Jpg缓存大小
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_GetJpgBuffer(DCHANDLE tHandle, unsigned char ** ucJpgBuffer, unsigned long * ulSize);

NET_API E_ReturnCode _stdcall Net_GetJpgBufferEx(DCHANDLE tHandle, unsigned char ** ucJpgBuffer, unsigned long * ulSize);

NET_API E_ReturnCode _stdcall Net_GetFrameData(DCHANDLE tHandle, unsigned char** data ,int *width, int *height);

/**********************************************************************
* 函数名称：Net_FreeBuffer
* 功能描述：释放缓存
* 输入参数：ucBuffer 待释放缓存指针(Net_GetJpgBuffer, Net_GetJpgBufferEx分配的内存)
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_FreeBuffer(void* pBuffer);

/**********************************************************************
* 函数名称：Net_StartRecord
* 功能描述：开始录像
* 输入参数：tHandle 相机句柄
*			strFile: 录像文件名
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_StartRecord(DCHANDLE tHandle, const char * strFile);

NET_API E_ReturnCode _stdcall Net_StartRecordEx(DCHANDLE tHandle, const char * strFile, int nSectionTime);

/**********************************************************************
* 函数名称：Net_StopRecord
* 功能描述：停止录像
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_StopRecord(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_SetDrawFunCallBack
* 功能描述：注册图像处理函数，用于在视频上画线
* 输入参数：tHandle 相机句柄
*			pDrawFun 回调函数指针
*			lpDrawFunData 回调函数上下文
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef void (CALLBACK *NET_DRAWFUNCALLBACK)(DCHANDLE tHandle,HDC hdc, int width, int height, void* pUser);
NET_API E_ReturnCode _stdcall Net_SetDrawFunCallBack(DCHANDLE tHandle, NET_DRAWFUNCALLBACK pDrawFun, void * lpDrawFunData);

/**********************************************************************
* 函数名称：Net_SetDrawFunCallBack
* 功能描述：注册图像数据导出回调
* 输入参数：tHandle 相机句柄
*			pDataOut 回调函数指针
*			pUser 回调函数上下文
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef void (CALLBACK *NET_DrawDataOut)(DCHANDLE tHandle, void * hdd, void * bmi, unsigned char* data, int width, int height, void* pUser);
NET_API E_ReturnCode _stdcall Net_SetDrawDataOut(DCHANDLE tHandle, NET_DrawDataOut pDrawDataOut, void * pUser);

/**********************************************************************
* 函数名称：Net_ShowNetSignal
* 功能描述：在视频画面显示网络信号强弱
* 输入参数：tHandle 相机句柄
*			niShowMode 显示模式,0:不显示,1:显示
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_ShowNetSignal(DCHANDLE tHandle, int niShowMode);

/**********************************************************************
* 函数名称：Net_ShowPlateRegion
* 功能描述：在视频画面显示车牌识别区
* 输入参数：tHandle 相机句柄
*			niShowMode 显示模式,0:不显示,1:显示
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_ShowPlateRegion(DCHANDLE tHandle, int niShowMode);

/**********************************************************************
* 函数名称：Net_UpdatePlateRegion
* 功能描述：更新视频画面车牌识别区
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_UpdatePlateRegion(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_StopVideo
* 功能描述：停止接收视频码流
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_StopVideo(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_QueryVideoState
* 功能描述：查询码流接收状态
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryVideoState(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_QueryConnState
* 功能描述：查询相机连接状态
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryConnState(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_ImageSnap
* 功能描述：图片抓拍，下发图片抓拍命令，通过Net_RegImageRecvEx注册回调函数接收图片信息
* 输入参数：tHandle 相机句柄
*			ptImageSnap  图片抓拍参数，可全部置0
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_ImageSnap(DCHANDLE tHandle, T_DCImageSnap *ptImageSnap);

/**********************************************************************
* 函数名称：Net_ParkingInfo
* 功能描述：下发车位上停车信息上报，通过Net_RegReportMessEx注册回调函数接收图片信息
* 输入参数：tHandle 相机句柄
*			ptRspParkingInfo  车位上停车信息参数，可全部置0
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_ParkingInfo(DCHANDLE tHandle, T_RspParkingInfo *ptRspParkingInfo);

/**********************************************************************
* 函数名称：Net_GetImage
* 功能描述：获取图片信息，如果使用该函数，需要调用Net_SetSnapMode将抓拍模式设置为连续模式
* 输入参数：tHandle 相机句柄
*			uiImageId 图片ID
*			ptImageInfo 车辆识别结果指针
*			ptPicInfo   图片缓冲区指针及大小
* 输出参数：ptImageInfo  图片中车辆信息
*			ptPicInfo  图片数据及图片大小
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_GetImage(DCHANDLE tHandle, unsigned int  uiImageId, T_ImageUserInfo *ptImageInfo, T_PicInfo *ptPicInfo);

/**********************************************************************
* 函数名称：Net_GateSetup
* 功能描述：闸机控制
* 输入参数：tHandle 相机句柄
*           ptControlGate 闸机控制参数指针，1开闸；2关闸；3停闸；
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_GateSetup(DCHANDLE tHandle,  T_ControlGate *ptControlGate);

/**********************************************************************
* 函数名称：Net_GetSdkVersion
* 功能描述：获取sdk版本信息
* 输入参数：szVersion 版本缓冲区
*		    ptLen   缓冲区大小
* 输出参数：szVersion sdk版本信息
*           ptLen   版本真实长度
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_GetSdkVersion(unsigned char *szVersion, unsigned int *ptLen);

#ifndef _E_SnapMode_
#define _E_SnapMode_
typedef enum
{
	SNAP_MODE_TOUCH = 0, /*触发抓拍*/
	SNAP_MODE_PERSIST,   /*连续抓拍*/
	SNAP_MODE_ALL,
}E_SnapMode;
#endif

/**********************************************************************
* 函数名称：Net_SetSnapMode
* 功能描述：设置相机抓拍模式
* 输入参数：tHandle	相机句柄
			niSnapMode 相机抓拍模式，见E_SnapMode，通过回调函数获取图片为触发抓拍模式，通过Net_GetImage获取图片信息，为连续抓拍模式
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_SetSnapMode(DCHANDLE tHandle, int niSnapMode);

/**********************************************************************
* 函数名称：Net_RegImageRecv
* 功能描述：通过注册回调函数，获取上报的图片信息及识别结果
			只需在SDK初始化成功后注册一次回调即可,多次注册以最后一次注册的回调函数为准
			推荐使用Net_RegImageRecvEx
* 输入参数：fCb 回调函数
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef int (CALLBACK *FGetImageCB)(DCHANDLE tHandle, unsigned int  uiImageId, T_ImageUserInfo *ptImageInfo, T_PicInfo *ptPicInfo);
NET_API E_ReturnCode _stdcall Net_RegImageRecv(FGetImageCB fCb);

/**********************************************************************
* 函数名称：Net_RegImageRecv2
* 功能描述：通过注册回调函数，获取上报的图片信息及识别结果，包括车标等信息，相比Net_RegImageRecv上报内容更丰富
			只需在SDK初始化成功后注册一次回调即可,多次注册以最后一次注册的回调函数为准
* 输入参数：fCb 回调函数
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef int (CALLBACK *FGetImageCB2)(DCHANDLE tHandle, unsigned int  uiImageId, T_ImageUserInfo2 *ptImageInfo, T_PicInfo *ptPicInfo);
NET_API E_ReturnCode _stdcall Net_RegImageRecv2(FGetImageCB2 fCb);

/**********************************************************************
* 函数名称：Net_RegImageRecvEx
* 功能描述：通过注册回调函数，获取上报的图片，实时识别结果通过该回调导出，Net_RegImageRecv的扩展函数，增加回调函数的上下文
			每建立一次链接必须注册一次否则不上报,同个链接多次注册以最后一次注册的回调函数为准
* 输入参数：tHandle 相机句柄
*			fCb 回调函数
			{
				tHandle 相机句柄
				uiImageId 上传的识别结果的类型，0为实时识别数据
				ptImageInfo 指向识别结果的指针
				ptPicInfo 识别结果图片的缓存区，若无图片，则里边指针为空
				pUser	回调函数上下文
			}
			pUser 回调函数上下文

* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef int (CALLBACK *FGetImageCbEx)(DCHANDLE tHandle,unsigned int  uiImageId, T_ImageUserInfo *ptImageInfo, T_PicInfo *ptPicInfo,void *pUser);
NET_API E_ReturnCode _stdcall Net_RegImageRecvEx(DCHANDLE tHandle, FGetImageCbEx fCb,void *pUser);

typedef int (CALLBACK *FGetImageCbEx2)(DCHANDLE tHandle,unsigned int  uiImageId, T_ImageUserInfo2 *ptImageInfo, T_PicInfo *ptPicInfo,void *pUser);
NET_API E_ReturnCode _stdcall Net_RegImageRecvEx2(DCHANDLE tHandle, FGetImageCbEx2 fCb,void *pUser);

/**********************************************************************
* 函数名称：MatchSpecialCode
* 功能描述：特征码比较
* 输入参数：ptSpecialCode1 特征码结构体指针
*			ptSpecialCode2  特征码结构体指针
* 输出参数：无  
* 返 回 值：返回分数[0,1]
***********************************************************************/
NET_API float _stdcall Net_MatchSpecialCode(T_SpecialCode * ptSpecialCode1, T_SpecialCode * ptSpecialCode2);

NET_API float _stdcall Net_MatchSpecialCode2(float fSpecialCode1[20], float fSpecialCode2[20]);

/**********************************************************************
* 函数名称：Net_RegOffLineImageRecvEx
* 功能描述：通过注册回调函数，获取脱机记录数据，包括车牌，车型等信息，当该函数被注册时，相机的脱机记录结果会上抛到该接口
* 输入参数：tHandle 相机句柄

			fCb 回调函数
			{
				tHandle 相机句柄
				uiImageId 上传的识别结果的类型，1为脱机记录数据
				ptImageInfo 指向识别结果的指针
				ptPicInfo 识别结果图片的缓存区，若无图片，则里边指针为空
				pUser	回调函数上下文
			}

			pUserData 回调函数上下文
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef int (CALLBACK *FGetOffLineImageCBEx)(DCHANDLE tHandle, unsigned int  uiImageId,  T_ImageUserInfo *ptImageInfo,T_PicInfo *ptPicInfo,void *pUserData);
NET_API E_ReturnCode _stdcall Net_RegOffLineImageRecvEx(DCHANDLE tHandle,FGetOffLineImageCBEx fCb,void *pUserData);

/**********************************************************************
* 函数名称：Net_RegOffLinePayRecord
* 功能描述：通过注册回调函数，获取出口相机脱机收费记录信息，包括车辆出入场信息，收费金额，会员类型等等
* 输入参数：tHandle 相机句柄
			fCb 回调函数
			{
				tHandle 相机句柄
				ucType	回调上抛消息类型，目前0为脱机收费记录；
				ptVehPayInfo 相机脱机收费记录信息； 
				uiLen		ptVehPayInfo结构体对应的长度；
				ptPicInfo	识别结果图片的缓存区；【脱机收费记录没有图片，则指针为空】需要图片可以获取脱机记录，自主去匹配图片
				pUserData 回调函数上下文；
			}
			pUserData 回调函数上下文
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef int (CALLBACK *FGetOffLinePayRecordCB)(DCHANDLE tHandle, unsigned char  ucType, T_VehPayRsp  *ptVehPayInfo, unsigned int uiLen,T_PicInfo *ptPicInfo,void *pUserData);
NET_API E_ReturnCode _stdcall Net_RegOffLinePayRecord(DCHANDLE tHandle,FGetOffLinePayRecordCB fCb,void *pUserData);

/**********************************************************************
* 函数名称：Net_GetPresentVehInfoAsCSV
* 功能描述：以CSV格式导出车辆在场信息表
* 输入参数：tHandle 相机句柄
*			ptGetPresentVehInfo 相机在场信息表参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_GetPresentVehInfoAsCSV(DCHANDLE tHandle, T_GetPrensentVehInfo *ptGetPresentVehInfo);

/**********************************************************************
* 函数名称：Net_SaveImageToJpeg
* 功能描述：截取当前图像，保存到指定路径,图片路径所在盘不能小于2M，否则返回 DC_MEMORY_LACK 内存申请失败
* 输入参数：tHandle 相机句柄
*			ucPathNmme 保存图像的路径
* 输出参数：无 
* 返 回 值：状态码
***********************************************************************/

NET_API E_ReturnCode _stdcall Net_SaveImageToJpeg(DCHANDLE tHandle,unsigned char *ucPathNmme);

/**********************************************************************
* 函数名称：Net_RegReportMessEx
* 功能描述：通过注册回调函数，获取上报消息；(请不要在此回调函数做阻塞操作)
* 输入参数：tHandle 相机句柄
			fCb 回调函数
			{
				tHandle 相机句柄
				ucType  消息类型，见E_ReportMess
				ptMessage 根据消息类型不同，对应的结构体不同；
				详见下表：	
				REPORT_MESS_MAC					T_MacInfo
				REPORT_MESS_ACE					T_Ave_Result
				REPORT_MESS_PARK_STATE			T_ParkRealTimeState
				REPORT_MESS_RESET_KEY_PRESS		T_ResetKeyPressState
				REPORT_MESS_RESET_VEH_INFO		T_VehResult
				REPORT_MESS_ASS_CAM_IP_SEARCH	T_AssCameraIpSearch
				REPORT_MESS_RS485_IN_DATA		T_RS485Data
				REPORT_MESS_LOOP_DETECTOR		T_IOStateRsp
				REPORT_VIDEO_DISTRICT_CHANGED   NULL
				REPORT_TRA_STAT_REPORT			T_DCTraStatReport
				REPORT_ASS_CAMERA_TYPE			T_AssCameraType
				REPORT_FILE_RECV_STATE			T_FileRecvResult
				REPORT_PS_PARKINGINFO			T_RspParkingInfo
				REPORT_PARK_NUM					T_ParkNum
				REPORT_CKECK_TALKBACK_BNT		NULL
				REPORT_4G_STATUS				T_T4GInfoParam
				REPORT_AUDIO_LINK				T_AudioLinkInfo;
				REPORT_WARNINGINFO				T_WarningInfo;
				REPORT_LPRINFO_EXT,				T_Lprinfo_ext;//单独上报车牌信息 不带图片
				pUserData 	回调函数上下文
			}
			pUserData 回调函数上下文
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef int (CALLBACK *FGetReportCBEx)(DCHANDLE tHandle,unsigned char ucType,void *ptMessage,void *pUserData);
NET_API E_ReturnCode _stdcall Net_RegReportMessEx(DCHANDLE tHandle, FGetReportCBEx fcb,void *pUserData);

/**********************************************************************
* 函数名称：DCSetSynTimePeriod
* 功能描述：设置SDK内部同步时间周期
* 输入参数：单位秒，当为0时，不启用内部同时
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_SetSynTimePeriod(unsigned short usSecTime);

/**********************************************************************
* 函数名称：Net_ParkNumSetup
* 功能描述：设置空余停车位
* 输入参数：tHandle 相机句柄
			ptParkNum 空余停车位参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ParkNumSetup(DCHANDLE tHandle, T_ParkNum *ptParkNum);

/**********************************************************************
* 函数名称：Net_QueryParkNumSetup
* 功能描述：查询空余停车位
* 输入参数：tHandle 相机句柄
			ptParkNum 空余停车位参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryParkNumSetup(DCHANDLE tHandle, T_ParkNum *ptParkNum);

/**********************************************************************
* 函数名称：Net_PayCountSetup
* 功能描述：设置缴费金额
* 输入参数：tHandle 相机句柄
			ptPayCount 缴费金额参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_PayCountSetup(DCHANDLE tHandle, T_PayCount *ptPayCount);

/**********************************************************************
* 函数名称：Net_SendRS485Data
* 功能描述：rs485数据透传接口，向RS485接口透传数据
* 输入参数：tHandle 相机句柄
*			ptRS485Data 透传RS485数据参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SendRS485Data(DCHANDLE tHandle, T_RS485Data *ptRS485Data);

/**********************************************************************
* 函数名称：Net_TransRS485Data
* 功能描述：rs485数据透传接口，向RS485接口透传数据
* 输入参数：tHandle 相机句柄
*			ucRs485Id RS485口的ID，从0编号
*			pRS485Data 指向待传数据的指针
*			ucDatalen 待传数据的长度，最大长度为256个字节
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_TransRS485Data(DCHANDLE tHandle, unsigned char ucRs485Id,unsigned char  *pRS485Data,unsigned char ucDatalen);

/**********************************************************************
* 函数名称：Net_TransRS485Data
* 功能描述：rs485数据透传接口，向RS485接口透传数据
* 输入参数：tHandle 相机句柄
*			ucRs485Id RS485口的ID，从0编号
*			pRS485Data 指向待传数据的指针
*			usDatalen 待传数据的长度，最大长度为1024个字节
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_TransRS485DataEx(DCHANDLE tHandle, unsigned char ucRs485Id,unsigned char  *pRS485Data,unsigned short usDatalen);

/**********************************************************************
* 函数名称：Net_TransRS485HexData
* 功能描述：rs485数据透传接口，向RS485接口透传16进制数据,数据格式参考（00 01 02 F1 F3 ...）,建议用Net_TransRS485HexDataEx
* 输入参数：tHandle 相机句柄
*			ucRs485Id RS485口的ID，从0编号
*			pRS485Data 指向待传数据的16进制字符串指针
*			ucDatalen 指向待传数据的16进制字符串长度,最大长度为256个
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_TransRS485HexData(DCHANDLE tHandle, unsigned char ucRs485Id,unsigned char  *pRS485Data,unsigned char ucDatalen);

/**********************************************************************
* 函数名称：Net_TransRS485HexDataEx
* 功能描述：rs485数据透传接口，向RS485接口透传16进制数据,数据格式参考（00 01 02 F1 F3 ...）, 对 Net_TransRS485HexData的修正,发送字节长度限制
* 输入参数：tHandle 相机句柄
*			ucRs485Id RS485口的ID，从0编号
*			pRS485Data 指向待传数据的16进制字符串指针
*			ucDatalen 指向待传数据的16进制字符串长度,最大长度为3072个(内部一次最多发送1024个16进制字节)
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_TransRS485HexDataEx(DCHANDLE tHandle, unsigned char ucRs485Id, unsigned char  *pRS485Data, unsigned int iDatalen);
/**********************************************************************
* 函数名称：Net_ReadRS485Data
* 功能描述：读取RS485输入的数据
* 输入参数：tHandle 相机句柄
*			ptRS485Data 读取RS485数据参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ReadRS485Data(DCHANDLE tHandle, T_RS485Data *ptRS485Data);

/**********************************************************************
* 函数名称：Net_BlackWhiteListSetup
* 功能描述：可循环调用该函数，将车牌信息按照指定格式写入到文件，再调用Net_BlackWhiteListSend将黑白名单导入到相机
			车牌字符必须为GB2312编码
* 输入参数：ptLprResult 指向存储白名单信息的内存
*			ptBlackWhiteListCount 本次传输的白名单的个数与写入白名单的路径
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_BlackWhiteListSetup(T_LprResult *ptLprResult,T_BlackWhiteListCount *ptBlackWhiteListCount);
/**********************************************************************
* 函数名称：Net_BlackWhiteListSend
* 功能描述：批量导入黑白名单到相机，字符编码必须为GB2312格式，适用于多条车牌与相机交互，当车牌数小于10条时，建议调用Net_SendBlackWhiteListByMess将白名单传入相机；
			车牌字符必须为GB2312编码
* 输入参数：tHandle 相机句柄
*			ptBalckWhiteList 相机黑白名单参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_BlackWhiteListSend(DCHANDLE tHandle, T_BlackWhiteList *ptBalckWhiteList);

/**********************************************************************
* 函数名称：Net_BlackWhiteListSendEx
* 功能描述：批量导入黑白名单到相机，字符编码必须为GB2312格式，适用于多条车牌与相机交互，当车牌数小于10条时，建议调用Net_SendBlackWhiteListByMessEx将白名单传入相机；
			车牌字符必须为GB2312编码
* 输入参数：tHandle 相机句柄
*			ptBalckWhiteList 相机黑白名单参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_BlackWhiteListSendEx(DCHANDLE tHandle, T_BlackWhiteList *ptBalckWhiteList);

/**********************************************************************
* 函数名称：Net_BlackWhiteListSendReportMess
* 功能描述：通过注册回调函数，上报导入白名单中不正确的车牌信息，配合Net_BlackWhiteListSend使用
* 输入参数：tHandle 相机句柄
*			fCb 回调函数
			{
				iErrCode 错误码 参见 E_BlackWhiteListErrorCode
				iLine >=0 不正确车牌的行数
				pPlateInfoPlateInfo 指向出错的车牌信息
				pUser	回调函数上下文
			}
			pUser 回调函数上下文

* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
typedef int (CALLBACK *FBlackWhiteListSendReportMess)(int iErrCode, int iLine, const char *pPlateInfo, void *pUser);
NET_API E_ReturnCode _stdcall Net_BlackWhiteListSendReportMess(DCHANDLE tHandle, FBlackWhiteListSendReportMess fCb, void *pUser);

/**********************************************************************
* 函数名称：Net_SendBlackWhiteListByMess
* 功能描述：通过消息将白名单导入到相机，适用于1到10条车牌信息与相机交互；当车牌数大于10条时，请参考批量导入接口Net_BlackWhiteListSend;
			车牌字符必须为GB2312编码
* 输入参数：tHandle 相机句柄
			pSendLprByMess	指向待传输车牌的信息
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SendBlackWhiteListByMess(DCHANDLE tHandle,T_SendLprByMess *ptSendLprByMess);

/**********************************************************************
* 函数名称：Net_DeleteAllBlackWhiteList
* 功能描述：删除相机内所有黑白名单
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_DeleteAllBlackWhiteList(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_ClearOfflineData
* 功能描述：清除脱机数据
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ClearOfflineData(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_QueryWhiteListByPlate
* 功能描述：通过车牌查询白名单内该车牌信息，车牌字符必须为GB2312编码
* 输入参数：tHandle 相机句柄
*			pPlateInfo 车牌号码
			ptLprResult 指向查询到的车牌信息
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryWhiteListByPlate(DCHANDLE tHandle, const char *pPlateInfo,T_RspLprResult *ptLprResult);

/**********************************************************************
* 函数名称：Net_GetBlackWhiteList
* 功能描述：导出相机黑白名单
* 输入参数：tHandle 相机句柄
*			ptBalckWhiteList 相机黑白名单参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_GetBlackWhiteList(DCHANDLE tHandle, T_GetBlackWhiteList *ptGetBalckWhiteList);

/**********************************************************************
* 函数名称：Net_GetBlackWhiteListAsCSV
* 功能描述：以CSV格式导出相机黑白名单
* 输入参数：tHandle 相机句柄
*			ptBalckWhiteList 相机黑白名单参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_GetBlackWhiteListAsCSV(DCHANDLE tHandle, T_GetBlackWhiteList *ptGetBalckWhiteList);

/**********************************************************************
* 函数名称：Net_GetBlackWhiteListAsCSVEx
* 功能描述：以CSV格式导出相机黑白名单
* 输入参数：tHandle 相机句柄
*			ptBalckWhiteList 相机黑白名单参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_GetBlackWhiteListAsCSVEx(DCHANDLE tHandle, T_GetBlackWhiteList *ptGetBalckWhiteList);

/**********************************************************************
* 函数名称：Net_SetControlCallBack
* 功能描述：通过注册该回调函数，获取相机的实时连接状态,相机连接状态见枚举E_ConnState
* 输入参数：pControlCallBack 回调函数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/

typedef void (CALLBACK *NET_CONTROLCALLBACK) (DCHANDLE tHandle,unsigned char ucCtrlConnState, void* pUser);
NET_API E_ReturnCode _stdcall Net_SetControlCallBack(NET_CONTROLCALLBACK pControlCallBack);

/**********************************************************************
* 函数名称：Net_SetControlCallBackEx
* 功能描述：通过注册该回调函数，获取相机的实时连接状态，Net_SetControlCallBack的扩展函数，增加回调函数上下文，相机连接状态见枚举E_ConnState
* 输入参数：tHandle 相机句柄
*			pControlCallBack 回调函数指针
			pUser 回调函数上下文
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/

typedef void (CALLBACK *NET_CONTROLCALLBACKEx) (DCHANDLE tHandle,unsigned char ucCtrlConnState, void* pUser);
NET_API E_ReturnCode _stdcall Net_SetControlCallBackEx(DCHANDLE tHandle,NET_CONTROLCALLBACKEx pControlCallBack, void* pUser);

/**********************************************************************
* 函数名称：Net_SetWhiteListMode
* 功能描述：设置白名单工作模式，即脱机使能，使能，不使能三种模式
* 输入参数：tHandle 相机句柄
*			ptWhiteListMode 白名单模式参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SetWhiteListMode(DCHANDLE tHandle, T_WhiteListMode *ptWhiteListMode);

/**********************************************************************
* 函数名称：Net_QueryWhiteListMode
* 功能描述：查询白名单工作模式
* 输入参数：tHandle 相机句柄
*			ptWhiteListMode 白名单模式参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryWhiteListMode(DCHANDLE tHandle,T_WhiteListMode *ptWhiteListMode);

/**********************************************************************
* 函数名称：Net_ExportWhiteListTemplate
* 功能描述：导出白名单模板
* 输入参数：szPath 导出路径
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ExportWhiteListTemplate(unsigned char *szPath);

/**********************************************************************
* 函数名称：Net_SLedTfgSetup
* 功能描述：设置屏显扩展内容
* 输入参数：tHandle 相机句柄
*			T_SLedSetup_tfg 屏显扩展内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SLedTfgSetup(DCHANDLE tHandle,T_SLedSetup_tfg *ptSLedSetup);

/**********************************************************************
* 函数名称：Net_QuerySLedTfgSetup
* 功能描述：查询屏显扩展内容
* 输入参数：tHandle 相机句柄
*			T_SLedSetup_tfg 屏显扩展内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QuerySLedTfgSetup(DCHANDLE tHandle,T_SLedSetup_tfg *ptSLedSetup);

/**********************************************************************
* 函数名称： Net_SLedSetupExt
* 功能描述：设置LED显示屏扩展内容
* 输入参数：tHandle 相机句柄
*			ptSLedSetupExt LED显示扩展内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SLedSetupExt(DCHANDLE tHandle,T_SLedSetupExt *ptSLedSetupExt);

/**********************************************************************
* 函数名称： Net_QuerySLedSetupExt
* 功能描述：查询LED显示屏内容
* 输入参数：tHandle 相机句柄
*			ptSLedSetupExt LED显示扩展内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QuerySLedSetupExt(DCHANDLE tHandle,T_SLedSetupExt *ptSLedSetupExt);

/**********************************************************************
* 函数名称：Net_LedSetup
* 功能描述：设置LED显示屏内容
* 输入参数：tHandle 相机句柄
*			ptLedSetup LED显示内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LedSetup(DCHANDLE tHandle,T_LedSetup *ptLedSetup);

/**********************************************************************
* 函数名称：Net_QueryLedSetup
* 功能描述：查询LED显示屏内容
* 输入参数：tHandle 相机句柄
*			ptLedSetup LED显示内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLedSetup(DCHANDLE tHandle,T_LedSetup *ptLedSetup);

/**********************************************************************
* 函数名称：Net_LedSetupEx
* 功能描述：设置LED显示屏内容
* 输入参数：tHandle 相机句柄
*			ptLedSetup LED显示内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LedSetupEx(DCHANDLE tHandle,T_LedSetup *ptLedSetup);

/**********************************************************************
* 函数名称：Net_QueryLedSetupEx
* 功能描述：查询LED显示屏内容
* 输入参数：tHandle 相机句柄
*			ptLedSetup LED显示内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLedSetupEx(DCHANDLE tHandle,T_LedSetup *ptLedSetup);

/**********************************************************************
* 函数名称：Net_LedLzSetup
* 功能描述：设置LED显示屏内容
* 输入参数：tHandle 相机句柄
*			ptLedLzSetup LED显示内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LedLzSetup(DCHANDLE tHandle,T_LZ_LedSetup *ptLedLzSetup);

/**********************************************************************
* 函数名称：Net_QueryLedLzSetup
* 功能描述：查询LED显示屏内容
* 输入参数：tHandle 相机句柄
*			ptLedLzSetup LED显示内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLedLzSetup(DCHANDLE tHandle,T_LZ_LedSetup *ptLedLzSetup);

/**********************************************************************
* 函数名称：Net_LedDcSetup
* 功能描述：设置LED显示屏内容
* 输入参数：tHandle 相机句柄
*			ptDCScreenSetup LED显示内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LedDcSetup(DCHANDLE tHandle,T_DCScreenSetup *ptDCScreenSetup);

/**********************************************************************
* 函数名称：Net_QueryLedDcSetup
* 功能描述：查询LED显示屏内容
* 输入参数：tHandle 相机句柄
*			ptDCScreenSetup LED显示内容参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLedDcSetup(DCHANDLE tHandle,T_DCScreenSetup *ptDCScreenSetup);

/**********************************************************************
* 函数名称：Net_RegOffLineClient
* 功能描述：即将当前客户端注册为岗亭端，将相机与当前客户端链接状态作为相机是否脱机的依据
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_RegOffLineClient(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_RegOffLineClientEx
* 功能描述：注册与反注册岗亭端，即将当前客户端注册为岗亭端，将相机与当前客户端链接状态作为相机是否脱机的依据
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_RegOffLineClientEx(DCHANDLE tHandle, T_RegState *ptRegState);

/**********************************************************************
* 函数名称：Net_ReadGPIOState
* 功能描述：读取指定接口的GPIO状态，即读取接入的车检器状态
* 输入参数：tHandle 相机句柄
			ucIndex  接口索引值，从0开始编号
			pucValue  指向返回的状态值的指针，0或1
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ReadGPIOState(DCHANDLE tHandle,unsigned char ucIndex,unsigned char *pucValue);

/**********************************************************************
* 函数名称：Net_WriteGPIOSate
* 功能描述：向指定接口的GPIO写入值，即向指定继电器写入状态。0为开路，1为短路
* 输入参数：tHandle 相机句柄
			ucIndex  接口索引值，从0开始编号
			ucValue  写入的状态值，0或1
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_WriteGPIOState(DCHANDLE tHandle,unsigned char ucIndex,unsigned char ucValue);

/**********************************************************************
* 函数名称：Net_WriteTwoEncpyption
* 功能描述：写入用户私有数据，用于二次加密
* 输入参数：tHandle 相机句柄
			pUserData	用户数据
*			uiDataLen 用户数据的长度
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_WriteTwoEncpyption(DCHANDLE tHandle,unsigned char *pUserData,unsigned int uiDataLen);

/**********************************************************************
* 函数名称：Net_ReadTwoEncpyption
* 功能描述：读出用户写入的私有数据
* 输入参数：tHandle 相机句柄
*			pBuff 用于存放读到的用户数据
			uiSizeBuff  用户数据缓冲区的大小,uiSizeBuff必须>=256
* 输出参数：无
* 返 回 值：返回值为实际用户数据的字节数，返回-1表示失败
***********************************************************************/ 
NET_API int _stdcall Net_ReadTwoEncpyption(DCHANDLE tHandle,  unsigned char *pBuff, unsigned int uiSizeBuff);

/**********************************************************************
* 函数名称：Net_TwoEncpyptionSet
* 功能描述：设置二次加密开启关闭
* 输入参数：tHandle 相机句柄
			ptTwoEncpyptionSet  二次加密设置结构体
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_TwoEncpyptionSet(DCHANDLE tHandle,  T_TwoEncpyptionSet *ptTwoEncpyptionSet);

/**********************************************************************
* 函数名称：Net_TwoEncpyptionAuth
* 功能描述：二次加密鉴权
* 输入参数：tHandle 相机句柄
			ptTwoEncpyptionAuth  二次加密鉴权结构体
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_TwoEncpyptionAuth(DCHANDLE tHandle,  T_TwoEncpyptionAuth *ptTwoEncpyptionAuth);

/**********************************************************************
* 函数名称：Net_TwoEncpyptionModify
* 功能描述：二次加密修改
* 输入参数：tHandle 相机句柄
			ptTwoEncpyptionModify  二次加密修改结构体
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_TwoEncpyptionModify(DCHANDLE tHandle,  T_TwoEncpyptionModify *ptTwoEncpyptionModify);

/**********************************************************************
* 函数名称：Net_TwoEncpyptionQuery
* 功能描述：二次加密查询开启关闭
* 输入参数：tHandle 相机句柄
			ptTwoEncpyptionQuery  二次加密开启关闭结构体
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_TwoEncpyptionQuery(DCHANDLE tHandle,  T_TwoEncpyptionQuery *ptTwoEncpyptionQuery);

/**********************************************************************
* 函数名称：Net_OffLinePayTest
* 功能描述：脱机收费测试
* 输入参数：tHandle 相机句柄
*			ptOfflineVehInfoTest 脱机收费测试结构体
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_OffLinePayTest(DCHANDLE tHandle, T_OfflineVehInfoTest *ptOfflineVehInfoTest);

/**********************************************************************
* 函数名称：Net_LensControl
* 功能描述：设置变倍马达
* 输入参数：tHandle 相机句柄
			ptLensControl 指向控制相机马达的结构体
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LensControl(DCHANDLE tHandle,T_LensControl *ptLensControl);

/**********************************************************************
* 函数名称：Net_AssLensControl
* 功能描述：设置变倍马达
* 输入参数：tHandle 相机句柄
			ptLensControl 指向控制相机马达的结构体
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_AssLensControl(DCHANDLE tHandle,T_LensControl *ptLensControl);

/**********************************************************************
* 函数名称：Net_ParkLedLightSetup
* 功能描述：设置LED灯亮度
* 输入参数：tHandle 相机句柄
			ptParkLedLightSetup  指向LED灯亮度设置的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ParkLedLightSetup(DCHANDLE tHandle,T_ParkLedLightSetup *ptParkLedLightSetup);

/**********************************************************************
* 函数名称：Net_ParkLedLightSetup
* 功能描述：查询LED灯亮度
* 输入参数：tHandle 相机句柄
			ptParkLedLightSetup  指向LED灯亮度设置的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryParkLedLightSetup(DCHANDLE tHandle,T_ParkLedLightSetup *ptParkLedLightSetup);

/**********************************************************************
* 函数名称：Net_ChangeUserPassword
* 功能描述：更改用户名和密码
* 输入参数：tHandle 相机句柄
			ptUserAccount  指向用户名和密码配置的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ModifyUserPassword(DCHANDLE tHandle,T_ModifyUserAccount *ptUserAccount);

/**********************************************************************
* 函数名称：Net_ModifyUserPort
* 功能描述：更改用户连接端口
* 输入参数：tHandle 相机句柄
			ptUserPort  指向端口的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ModifyUserPort(DCHANDLE tHandle,T_UserPort *ptUserPort);

/**********************************************************************
* 函数名称：Net_SetWLFuzzyMatchMode
* 功能描述：设置白名单模糊匹配模式
* 输入参数：tHandle 相机句柄
			ptWlFuzzyMatch  指向模糊匹配规则的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SetWLFuzzyMatchMode(DCHANDLE tHandle,T_WLFuzzyMatch *ptWlFuzzyMatch);

/**********************************************************************
* 函数名称：Net_QueryWLFuzzyMatchMode
* 功能描述：查询白名单模糊匹配模式
* 输入参数：tHandle 相机句柄
			ptWlFuzzyMatch  指向模糊匹配规则的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryWLFuzzyMatchMode(DCHANDLE tHandle,T_WLFuzzyMatch *ptWlFuzzyMatch);

/**********************************************************************
* 函数名称：Net_ManulWiperOpen
* 功能描述：手动开启雨刷
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ManulWiperOpen(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_ManulWiperClose
* 功能描述：手动关闭雨刷
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ManulWiperClose(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_SetOffLinePayMode
* 功能描述：设置脱机收费模式，即脱机使能，使能，不使能
* 输入参数：tHandle 相机句柄
			ptOffLinePayMode  指向脱机收费模式的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SetOffLinePayMode(DCHANDLE tHandle,T_OffLinePayMode *ptOffLinePayMode);

/**********************************************************************
* 函数名称：Net_QueryOffLinePayMode
* 功能描述：查询脱机收费模式
* 输入参数：tHandle 相机句柄
			ptOffLinePayMode  指向脱机收费模式的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryOffLinePayMode(DCHANDLE tHandle,T_OffLinePayMode *ptOffLinePayMode);

/**********************************************************************
* 函数名称：Net_SetOffLinePayRule
* 功能描述：设置脱机收费规则
* 输入参数：tHandle 相机句柄
			ptOffLinePayRule  指向脱机收费规则的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SetOffLinePayRule(DCHANDLE tHandle,T_PayRule *ptOffLinePayRule);

/**********************************************************************
* 函数名称：Net_QueryOffLinePayRule
* 功能描述：查询脱机收费规则
* 输入参数：tHandle 相机句柄
			ptOffLinePayRule  指向脱机收费规则的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryOffLinePayRule(DCHANDLE tHandle,T_PayRule *ptOffLinePayRule);

/**********************************************************************
* 函数名称：Net_SetGateAutoOpen
* 功能描述：设置出入口相机自动抬闸配置
* 输入参数：tHandle 相机句柄
			ptAutoControlGate  指向出入口相机自动抬闸规则的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SetGateAutoOpen(DCHANDLE tHandle,T_AutoControlGate *ptAutoControlGate);

/**********************************************************************
* 函数名称：Net_QueryGateAutoOpen
* 功能描述：查询出入口相机自动抬闸配置
* 输入参数：tHandle 相机句柄
			ptAutoControlGate  指向出入口相机自动抬闸规则的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryGateAutoOpen(DCHANDLE tHandle,T_AutoControlGate *ptAutoControlGate);

/**********************************************************************
* 函数名称：Net_SyncConfigByMulticast
* 功能描述：通过组播同步相机配置到其他相机
* 输入参数：tHandle 相机句柄
			ptSyncConfigByMuticast  指向同步相机配置规则的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SyncConfigByMulticast(DCHANDLE tHandle,T_SyncConfigByMuticast *ptSyncConfigByMuticast);

/**********************************************************************
* 函数名称：Net_SetVideoRotate
* 功能描述：设置视频旋转
* 输入参数：tHandle 相机句柄
			ptVideoRotate  指向视频旋转的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SetVideoRotate(DCHANDLE tHandle,T_VideoRotate *ptVideoRotate);

/**********************************************************************
* 函数名称：Net_QueryVideoRotate
* 功能描述：查询视频旋转
* 输入参数：tHandle 相机句柄
			ptVideoRotate  指向视频旋转的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryVideoRotate(DCHANDLE tHandle,T_VideoRotate *ptVideoRotate);

/**********************************************************************
* 函数名称：Net_SetAudioVol
* 功能描述：设置语音音量
* 输入参数：tHandle 相机句柄
			ptAudioVol  指向语音音量的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SetAudioVol(DCHANDLE tHandle,T_AudioVol *ptAudioVol);

/**********************************************************************
* 函数名称：Net_QueryAudioVol
* 功能描述：查询语音音量
* 输入参数：tHandle 相机句柄
			ptAudioVol  指向语音音量的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryAudioVol(DCHANDLE tHandle,T_AudioVol *ptAudioVol);

/**********************************************************************
* 函数名称：Net_AudioTalkBack
* 功能描述：语音对讲设置
* 输入参数：tHandle 相机句柄
			ptAudioTalkBack  指向语音对讲的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_AudioTalkBack(DCHANDLE tHandle, T_AudioTalkBack *ptAudioTalkBack);

/**********************************************************************
* 函数名称：Net_StartTalk
* 功能描述：开启语音对讲
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_StartTalk(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_StopTalk
* 功能描述：关闭语音对讲
* 输入参数：tHandle 相机句柄
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_StopTalk(DCHANDLE tHandle);

NET_API E_ReturnCode _stdcall Net_StartRecordCameraVoice(char * strFilePath);
NET_API E_ReturnCode _stdcall Net_StopRecordCameraVoice();
NET_API E_ReturnCode _stdcall Net_StartRecordPcVoice(char * strFilePath);
NET_API E_ReturnCode _stdcall Net_StopRecordPcVoice();


///**********************************************************************
//* 函数名称：Net_QueryTalkConnState
//* 功能描述：查询SDK对对讲模块是否在使用中
//* 输入参数：tHandle 相机句柄
//* 输出参数：无
//* 返 回 值：状态码 如任何一台相机开启对讲则返回 DC_OBJ_BUSY，没在使用则返回 DC_NO_ERROR
//***********************************************************************/
//NET_API E_ReturnCode _stdcall Net_QueryTalkConnState(DCHANDLE tHandle);

/**********************************************************************
* 函数名称：Net_QueryAudioLinkinfo
* 功能描述：查询相机是否已在对讲
* 输入参数：tHandle 相机句柄
*			ptAudioLinkinfo 链接状态指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryAudioLinkinfo(DCHANDLE tHandle, T_AudioLinkInfo *ptAudioLinkinfo);

/**********************************************************************
* 函数名称：Net_RegTalkConnStateCallBack
* 功能描述：注册相机语音对讲链接状态上报,全局回调接口只需要注册一次即可，请不要在回调函数中做长时间的阻塞操作
* 输入参数：pTalkConnStateCallBack 回调函数
			user 用户数据
* 输出参数：连接状态 ucCtrlConnState 详见 E_TalkConnState
* 返 回 值：状态码 如对讲不是开启状态 则返回 DC_OBJ_UNEXIST，对讲开启中则返回 DC_NO_ERROR
***********************************************************************/
typedef void (_stdcall *fTalkConnStateCallBack)(DCHANDLE tHandle,unsigned char ucCtrlConnState, void* pConnStateUser);
NET_API E_ReturnCode _stdcall Net_RegTalkConnStateCallBack(fTalkConnStateCallBack pTalkConnStateCallBack, void *user);

/**********************************************************************
* 函数名称：Net_ImportBlackWhiteList
* 功能描述：导入相机黑白名单
* 输入参数：tHandle 相机句柄
*			ptBalckWhiteList 相机黑白名单参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ImportBlackWhiteList(DCHANDLE tHandle, T_BlackWhiteList *ptBalckWhiteList);

NET_API E_ReturnCode _stdcall Net_ImportBlackWhiteListEx(DCHANDLE tHandle, T_BlackWhiteList *ptBalckWhiteList);

NET_API E_ReturnCode _stdcall Net_ImportBlackWhiteListCy(DCHANDLE tHandle, T_BlackWhiteList *ptBalckWhiteList);

/**********************************************************************
* 函数名称：Net_ExportBlackWhiteList
* 功能描述：导出相机黑白名单
* 输入参数：tHandle 相机句柄
*			ptGetBalckWhiteList 相机黑白名单参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ExportBlackWhiteList(DCHANDLE tHandle, T_GetBlackWhiteList *ptGetBalckWhiteList);

NET_API E_ReturnCode _stdcall Net_ExportBlackWhiteListAsCSV(DCHANDLE tHandle, T_GetBlackWhiteList *ptGetBalckWhiteList);

NET_API E_ReturnCode _stdcall Net_ExportBlackWhiteListCyAsCSV(DCHANDLE tHandle, T_GetBlackWhiteList *ptGetBalckWhiteList);


/**********************************************************************
* 函数名称：Net_ImportRePlate
* 功能描述：导入车牌后处理规则
* 输入参数：tHandle 相机句柄
*			strFile 文件名
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ImportRePlate(DCHANDLE tHandle, const char * strFile);

/**********************************************************************
* 函数名称：Net_ImportCA
* 功能描述：导入后台通信SSL的CA证书
* 输入参数：tHandle 相机句柄
*			strFile 文件名
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ImportCA(DCHANDLE tHandle, const char * strFile);

/**********************************************************************
* 函数名称：Net_ExportRePlate
* 功能描述：导出车牌后处理规则
* 输入参数：tHandle 相机句柄
*			strFile 文件名
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ExportRePlate(DCHANDLE tHandle, const char * strFile);

/**********************************************************************
* 函数名称：Net_SetCloudParam
* 功能描述：设置远程维护配置参数
* 输入参数：tHandle 相机句柄
			ptCloudParam  指向远程配置维护参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SetCloudParam(DCHANDLE tHandle, T_CloudParam *ptCloudParam);

/**********************************************************************
* 函数名称：Net_QueryCloudParam
* 功能描述：查询远程维护配置参数
* 输入参数：tHandle 相机句柄
			ptCloudParam  指向远程配置维护参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryCloudParam(DCHANDLE tHandle, T_CloudParam *ptCloudParam);

/**********************************************************************
* 函数名称：Net_QueryIOState
* 功能描述：查询IO状态
* 输入参数：tHandle 相机句柄
			ptQueryIOState  指IO状态参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryIOState(DCHANDLE tHandle, T_QueryIOState *ptQueryIOState);

/**********************************************************************
* 函数名称：Net_Wired4GSet
* 功能描述：设置连接外网类型
* 输入参数：tHandle 相机句柄
			ptWired4GSet  指向连接外网类型的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_Wired4GSet(DCHANDLE tHandle, T_Wired4GSet *ptWired4GSet);

/**********************************************************************
* 函数名称：Net_QueryWired4GSet
* 功能描述：查询连接外网类型
* 输入参数：tHandle 相机句柄
			ptWired4GSet  指连接外网类型参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryWired4GSet(DCHANDLE tHandle, T_Wired4GSet *ptWired4GSet);

/**********************************************************************
* 函数名称：Net_QueryControlGateQueue
* 功能描述：查询队列模式
* 输入参数：tHandle 相机句柄
			ptControlGateQueue  指向结构体指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryControlGateQueue(DCHANDLE tHandle,T_ControlGateQueue *ptControlGateQueue);

/**********************************************************************
* 函数名称：Net_ControlGateQueue
* 功能描述：队列模式设置
* 输入参数：tHandle 相机句柄
			ptControlGateQueue  指向机构体指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ControlGateQueue(DCHANDLE tHandle, T_ControlGateQueue *ptControlGateQueue);

/**********************************************************************
* 函数名称：Net_LcdSetup
* 功能描述：LCD显示屏配置
* 输入参数：tHandle 相机句柄
*			ptLcdShowSetup
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_LcdSetup(DCHANDLE tHandle,T_LcdShowSetup *ptLcdShowSetup);

/**********************************************************************
* 函数名称：Net_LcdEnableSetup
* 功能描述：LCD显示屏配置查询
* 输入参数：tHandle 相机句柄
*			ptLcdShowSetup
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryLcdSetup(DCHANDLE tHandle,T_LcdShowSetup *ptLcdShowSetup);

/**********************************************************************
* 函数名称：Net_LcdInContentSetup
* 功能描述：LCD 入口屏显内容配置
* 输入参数：tHandle 相机句柄
*			ptLCdSetup_in
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_LcdInContentSetup(DCHANDLE tHandle,T_SLCdSetup *ptLCdSetup);

/**********************************************************************
* 函数名称：Net_QueryLcdInContentSetup
* 功能描述：LCD 入口屏显内容配置查询
* 输入参数：tHandle 相机句柄
*			ptLCdSetup_in
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryLcdInContentSetup(DCHANDLE tHandle,T_SLCdSetup *ptLCdSetup);

/**********************************************************************
* 函数名称：Net_LcdOutContentSetup
* 功能描述：LCD出口屏内容配置
* 输入参数：tHandle 相机句柄
*			ptLCdSetup_out
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_LcdOutContentSetup(DCHANDLE tHandle,T_SLCdSetup *ptLCdSetup);


/**********************************************************************
* 函数名称：Net_QueryLcdOutContentSetup
* 功能描述：LCD出口屏内容配置查询
* 输入参数：tHandle 相机句柄
*			ptLCdSetup_out
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryLcdOutContentSetup(DCHANDLE tHandle,T_SLCdSetup *ptLCdSetup);

/**********************************************************************
* 函数名称：Net_LcdGUIContentSetup
* 功能描述：LCD显示屏GUI内容配置
* 输入参数：tHandle 相机句柄
*			ptDisplayContent
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_LcdGUIContentSetup(DCHANDLE tHandle,T_DisplayContent *ptDisplayContent);

/**********************************************************************
* 函数名称：Net_QueryLcdGUIContentSetup
* 功能描述：LCD显示屏GUI内容配置查询
* 输入参数：tHandle 相机句柄
*			ptDisplayContent
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryLcdGUIContentSetup(DCHANDLE tHandle,T_DisplayContent *ptDisplayContent);

/**********************************************************************
* 函数名称：Net_LcdGUIADSetup
* 功能描述：LCD显示屏GUI内容配置
* 输入参数：tHandle 相机句柄
*			ptLCdSetup_out
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_LcdGUIADSetup(DCHANDLE tHandle,T_ADShowSet *ptADShowSet);

/**********************************************************************
* 函数名称：Net_QueryLcdGUIADSetup
* 功能描述：LCD显示屏GUI内容配置查询
* 输入参数：tHandle 相机句柄
*			ptADShowSet
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryLcdGUIADSetup(DCHANDLE tHandle,T_ADShowSet *ptADShowSet);

/**********************************************************************
* 函数名称：Net_LcdUpADSetup
* 功能描述：LCD上区广告内容配置
* 输入参数：tHandle 相机句柄
*			ptUADSetup
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_LcdUpADSetup(DCHANDLE tHandle,T_UADSetup *ptUADSetup);

/**********************************************************************
* 函数名称：Net_QueryLcdUpADSetup
* 功能描述：LCD上区广告内容配置查询
* 输入参数：tHandle 相机句柄
*			ptUADSetup
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryLcdUpADSetup(DCHANDLE tHandle,T_UADSetup *ptUADSetup);

/**********************************************************************
* 函数名称：Net_LcdDADInSetup
* 功能描述：LCD下区入口广告内容配置
* 输入参数：tHandle 相机句柄
*			ptUADSetup
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_LcdDADInSetup(DCHANDLE tHandle,T_DADSetup *ptDADSetup);

/**********************************************************************
* 函数名称：Net_QueryLcdDADInSetup
* 功能描述：LCD下区入口广告内容配置查询
* 输入参数：tHandle 相机句柄D
*			ptUADSetup
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryLcdDADInSetup(DCHANDLE tHandle,T_DADSetup *ptDADSetup);

/**********************************************************************
* 函数名称：Net_LcdDADOutSetup
* 功能描述：LCD下区出口广告内容配置
* 输入参数：tHandle 相机句柄
*			ptUADSetup
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_LcdDADOutSetup(DCHANDLE tHandle,T_DADSetup *ptDADSetup);

/**********************************************************************
* 函数名称：Net_QueryLcdDADOutSetup
* 功能描述：LCD下区出口广告内容配置查询
* 输入参数：tHandle 相机句柄D
*			ptUADSetup
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryLcdDADOutSetup(DCHANDLE tHandle,T_DADSetup *ptDADSetup);

/**********************************************************************
* 函数名称：Net_SetFRTKChange
* 功能描述：FRTK定制收费模式设置
* 输入参数：tHandle 相机句柄
			ptChangeParam  指向机构体指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SetFRTKChange(DCHANDLE tHandle, T_CHARGE_PARAM_FRTK *ptChangeParam);

/**********************************************************************
* 函数名称：Net_QueryFRTKChange
* 功能描述：FRTK定制收费模式获取
* 输入参数：tHandle 相机句柄
			ptChangeParam  指向机构体指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryFRTKChange(DCHANDLE tHandle, T_CHARGE_PARAM_FRTK *ptChangeParam);

/**********************************************************************
* 函数名称：Net_ImportFRTKCarFee
* 功能描述：导入FRTK车辆脱机收费文件
* 输入参数：tHandle 相机句柄
*			strFile 文件名
*           eFeeType 收费类型
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ImportFRTKCarFee(DCHANDLE tHandle, const char * strFile,E_FRTKCarFee_Type eFeeType);

/**********************************************************************
* 函数名称：Net_ExportFRTKCarFee
* 功能描述：导出FRTK车辆脱机收费文件
* 输入参数：tHandle 相机句柄
*			T_ExportFRTKCarFee 导出参数
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ExportFRTKCarFee(DCHANDLE tHandle, T_ExportFRTKCarFee* ptParam);

/**********************************************************************
* 函数名称：Net_QueryVideoUADInfo
* 功能描述：LCD文件转码状态查询
* 输入参数：tHandle 相机句柄
			ptVideoUADInfo  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryVideoUADInfo(DCHANDLE tHandle, T_VideoUADInfo *ptVideoUADInfo);

/**********************************************************************
* 函数名称：Net_LcdOutShowMode
* 功能描述：LCD屏显示方式
* 输入参数：tHandle 相机句柄
*			ptLCdShowMode
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_LcdOutShowMode(DCHANDLE tHandle,T_LcdShowMode *ptLCdShowMode);

/**********************************************************************
* 函数名称：Net_QueryLcdOutShowMode
* 功能描述：LCD屏显示方式查询
* 输入参数：tHandle 相机句柄
*			ptLCdShowMode
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/
NET_API E_ReturnCode _stdcall Net_QueryLcdOutShowMode(DCHANDLE tHandle,T_LcdShowMode *ptLCdShowMode);

/**********************************************************************
* 函数名称：Net_LcdScreenSizeSetup
* 功能描述：LCD 屏幕尺寸设置
* 输入参数：tHandle 相机句柄
			ptLcdScreenSizeSetup  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LcdScreenSizeSetup(DCHANDLE tHandle, T_LcdScreenSize *ptLcdScreenSizeSetup);

/**********************************************************************
* 函数名称：Net_QueryLcdScreenSize
* 功能描述：LCD 屏幕尺寸查询
* 输入参数：tHandle 相机句柄
			ptLcdScreenSizeSetup  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLcdScreenSize(DCHANDLE tHandle, T_LcdScreenSize *ptLcdScreenSizeSetup);

/**********************************************************************
* 函数名称：Net_MediaVolSetup
* 功能描述：媒体音量设置
* 输入参数：tHandle 相机句柄
			ptMediaVolSetup  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_MediaVolSetup(DCHANDLE tHandle, T_AvAudioVol *ptMediaVolSetup);

/**********************************************************************
* 函数名称：Net_QueryMediaVol
* 功能描述：查询媒体音量
* 输入参数：tHandle 相机句柄
			ptMediaVolSetup  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryMediaVol(DCHANDLE tHandle, T_AvAudioVol *ptMediaVolSetup);

/**********************************************************************
* 函数名称：Net_PresetCameraCfgSetup
* 功能描述：设置摄像头参数时段配置
* 输入参数：tHandle 相机句柄
			ptPresetCameraCfg  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_PresetCameraTimeSetup(DCHANDLE tHandle, T_PresetCameraCfg *ptPresetCameraCfg);

/**********************************************************************
* 函数名称：Net_QueryPresetCameraCfg
* 功能描述：查询摄像头参数时段配置
* 输入参数：tHandle 相机句柄
			ptPresetCameraCfg  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryPresetCameraTimeSetup(DCHANDLE tHandle, T_PresetCameraCfg *ptPresetCameraCfg);

/**********************************************************************
* 函数名称：Net_LcdDInfoRtime
* 功能描述：设置实时显示信息
* 输入参数：tHandle 相机句柄
			ptLcdDInfoRtime  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LcdDInfoRtime(DCHANDLE tHandle, T_LcdDInfoRtime *ptLcdDInfoRtime);

/**********************************************************************
* 函数名称：Net_LcdShowQRCode
* 功能描述：收费二维码显示设置
* 输入参数：tHandle 相机句柄
			ptLcdShowQRCode  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LcdShowQRCode(DCHANDLE tHandle, T_LcdShowQRCode *ptLcdShowQRCode);

/**********************************************************************
* 函数名称：Net_LcdRTAudioPlay
* 功能描述：LCD实时语音播报发送
* 输入参数：tHandle 相机句柄
			ptLcdRTAudioPlay  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LcdRTAudioPlay(DCHANDLE tHandle, T_LcdRTAudioPlay *ptLcdRTAudioPlay);


/**********************************************************************
* 函数名称：Net_ExportAdvertFile
* 功能描述：导出转码成功后的广告文件
* 输入参数：tHandle 相机句柄
*			ptExportAdvertFile 指向参数的指针         
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_ExportAdvertFile(DCHANDLE tHandle, T_ExportAdvertFile *ptExportAdvertFile);

/**********************************************************************
* 函数名称：Net_LcdAdAudioMode
* 功能描述：广告播放模式配置
* 输入参数：tHandle 相机句柄
			ptLcdAdAudioMode  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LcdAdAudioMode(DCHANDLE tHandle, T_LcdAdAudioMode *ptLcdAdAudioMode);

/**********************************************************************
* 函数名称：Net_LcdFontAlign
* 功能描述：设置LCD文字对齐方式
* 输入参数：tHandle 相机句柄
			ptLcdFontAlign  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LcdFontAlign(DCHANDLE tHandle, T_LcdFontAlign *ptLcdFontAlign);

/**********************************************************************
* 函数名称：Net_QueryLcdFontAlign
* 功能描述：查询LCD文字对齐方式
* 输入参数：tHandle 相机句柄
			ptLcdFontAlign  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLcdFontAlign(DCHANDLE tHandle, T_LcdFontAlign *ptLcdFontAlign);

/**********************************************************************
* 函数名称：Net_DevQuadrillage
* 功能描述：设置设备经纬度
* 输入参数：tHandle 相机句柄
			ptDevQuadrillage  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_DevQuadrillage(DCHANDLE tHandle, T_DevQuadrillage *ptDevQuadrillage);

/**********************************************************************
* 函数名称：Net_QueryDevQuadrillage
* 功能描述：查询设备经纬度
* 输入参数：tHandle 相机句柄
			ptDevQuadrillage  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryDevQuadrillage(DCHANDLE tHandle, T_DevQuadrillage *ptDevQuadrillage);

/**********************************************************************
* 函数名称：Net_AdtgDeviceParam
* 功能描述：设置adtg设备信息
* 输入参数：tHandle 相机句柄
			ptLcdFontAlign  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_AdtgDeviceParam(DCHANDLE tHandle, T_AdtgDeviceParam *ptAdtgDeviceParam);

/**********************************************************************
* 函数名称：Net_QueryAdtgDeviceParam
* 功能描述：查询adtg设备信息
* 输入参数：tHandle 相机句柄
			ptLcdFontAlign  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryAdtgDeviceParam(DCHANDLE tHandle, T_AdtgDeviceParam *ptAdtgDeviceParam);

/**********************************************************************
* 函数名称：Net_LockParkingSpace
* 功能描述：设置车位配置信息
* 输入参数：tHandle 相机句柄
			ptLockParkingSpace  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LockParkingSpace(DCHANDLE tHandle, T_LockParkingSpace *ptLockParkingSpace);

/**********************************************************************
* 函数名称：Net_QueryLockParkingSpace
* 功能描述：查询车位配置信息
* 输入参数：tHandle 相机句柄
			ptLockParkingSpace  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLockParkingSpace(DCHANDLE tHandle, T_LockParkingSpace *ptLockParkingSpace);

/**********************************************************************
* 函数名称：Net_LockParkingSpaceLock
* 功能描述：设置车位锁配置信息
* 输入参数：tHandle 相机句柄
			ptLockParkingSpaceLock  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LockParkingSpaceLock(DCHANDLE tHandle, T_LockParkingSpaceLock *ptLockParkingSpaceLock);

/**********************************************************************
* 函数名称：Net_QueryLockParkingSpaceLock
* 功能描述：查询车位锁配置信息
* 输入参数：tHandle 相机句柄
			ptLockParkingSpaceLock  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLockParkingSpaceLock(DCHANDLE tHandle, T_LockParkingSpaceLock *ptLockParkingSpaceLock);

/**********************************************************************
* 函数名称：Net_LockRemoteCtrl
* 功能描述：设置车位锁配置信息
* 输入参数：tHandle 相机句柄
			ptLockRemoteCtrl  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LockRemoteCtrl(DCHANDLE tHandle, T_LockRemoteCtrl *ptLockRemoteCtrl);

/**********************************************************************
* 函数名称：Net_QueryLockRemoteCtrl
* 功能描述：查询车位锁配置信息
* 输入参数：tHandle 相机句柄
			ptLockRemoteCtrl  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLockRemoteCtrl(DCHANDLE tHandle, T_LockRemoteCtrl *ptLockRemoteCtrl);

/**********************************************************************
* 函数名称：Net_LockTriggerType
* 功能描述：设置触发控锁配置信息
* 输入参数：tHandle 相机句柄
			ptLockTriggerType  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LockTriggerType(DCHANDLE tHandle, T_LockTriggerType *ptLockTriggerType);

/**********************************************************************
* 函数名称：Net_QueryLockTriggerType
* 功能描述：查询触发控锁配置信息
* 输入参数：tHandle 相机句柄
			ptLockTriggerType  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLockTriggerType(DCHANDLE tHandle, T_LockTriggerType *ptLockTriggerType);

/**********************************************************************
* 函数名称：Net_LampTest
* 功能描述：测试灯控
* 输入参数：tHandle 相机句柄
			ptLampTest  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LampTest(DCHANDLE tHandle, T_LampTest *ptLampTest);

/**********************************************************************
* 函数名称：Net_HttpUpImageMode
* 功能描述：设置触发控锁配置信息
* 输入参数：tHandle 相机句柄
			ptHttpUpImageMode  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_HttpUpImageMode(DCHANDLE tHandle, T_HttpUpImageMode *ptHttpUpImageMode);

/**********************************************************************
* 函数名称：Net_QueryHttpUpImageMode
* 功能描述：查询触发控锁配置信息
* 输入参数：tHandle 相机句柄
			ptHttpUpImageMode  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryHttpUpImageMode(DCHANDLE tHandle, T_HttpUpImageMode *ptHttpUpImageMode);

/**********************************************************************
* 函数名称：Net_DeleteBlackWhiteList
* 功能描述：删除相机内所有白名单、白名单、黑白名单
* 输入参数：tHandle 相机句柄
			ptDeleteLprMode 
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_DeleteBlackWhiteList(DCHANDLE tHandle, T_DeleteLprMode *ptDeleteLprMode);

/**********************************************************************
* 函数名称：Net_QueryBlackListByPlate
* 功能描述：通过车牌查询黑名单内该车牌信息，车牌字符必须为GB2312编码
* 输入参数：tHandle 相机句柄
*			pPlateInfo 车牌号码
			ptLprResult 指向查询到的车牌信息
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryBlackListByPlate(DCHANDLE tHandle, const char *pPlateInfo,T_RspLprResult *ptLprResult);

/**********************************************************************
* 函数名称：Net_SetBlackListMode
* 功能描述：设置黑名单工作模式，使能，不使能2种模式
* 输入参数：tHandle 相机句柄
*			ptBlackListMode 白名单模式参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_SetBlackListMode(DCHANDLE tHandle, T_BlackListMode *ptBlackListMode);

/**********************************************************************
* 函数名称：Net_QueryBlackListMode
* 功能描述：查询黑名单工作模式
* 输入参数：tHandle 相机句柄
*			ptBlackListMode 白名单模式参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryBlackListMode(DCHANDLE tHandle,T_BlackListMode *ptBlackListMode);

/**********************************************************************
* 函数名称：Net_LockIoOutInfo
* 功能描述：设置IO灯控配置
* 输入参数：tHandle 相机句柄
*			ptLockIoOutInfo 白名单模式参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LockIoOutInfo(DCHANDLE tHandle, T_LockIoOutInfo *ptLockIoOutInfo);

/**********************************************************************
* 函数名称：Net_QueryLockIoOutInfo
* 功能描述：查询IO灯控配置
* 输入参数：tHandle 相机句柄
*			ptLockIoOutInfo 白名单模式参数指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_QueryLockIoOutInfo(DCHANDLE tHandle,T_LockIoOutInfo *ptLockIoOutInfo);

/**********************************************************************
* 函数名称：Net_LockIoOutTestInfo
* 功能描述：IO输出测试
* 输入参数：tHandle 相机句柄
			ptLockIoOutTestInfo  指向参数的指针
* 输出参数：无
* 返 回 值：状态码
***********************************************************************/ 
NET_API E_ReturnCode _stdcall Net_LockIoOutTestInfo(DCHANDLE tHandle, T_LockIoOutTestInfo *ptLockIoOutTestInfo);

#ifdef __cplusplus
}
#endif
#endif

