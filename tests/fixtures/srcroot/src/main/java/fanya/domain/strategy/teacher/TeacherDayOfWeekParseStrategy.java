package fanya.domain.strategy.teacher;

import com.alibaba.fastjson2.JSONArray;
import fanya.services.CommonMethods;
import fanya.domain.constrains.Constrain;
import fanya.domain.constrains.Constrains;
import fanya.domain.constrains.TargetKey;
import fanya.domain.strategy.OperatorType;
import fanya.domain.strategy.ParseStrategy;

import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class TeacherDayOfWeekParseStrategy implements ParseStrategy<TeacherParseContext> {
    @Override
    public void parse(Object right, OperatorType operator, TeacherParseContext context) {
        Constrains constrains = context.getConstrains();
        String level = context.getLevel();
        String description = context.getDescription();
        JSONArray teacherIds = context.getTeacherIds();
        Map<String, Set<Long>> dayOfWeekToTimeslotIds = constrains.getDayOfWeekToTimeslotIds();

        Constrain<Long> teacherAllowed = ensureTeacherAllowedInitialized(constrains);

        if (description != null) {
            CommonMethods.setDescription(description, teacherAllowed);
        }

        List<String> strings = CommonMethods.extractStringList(right);
        Set<Long> allowTimeslotIds = new HashSet<>();

        Set<Long> allTimeslotIds = constrains.getAllTimeslotIds();
        if (allTimeslotIds == null) {
            allTimeslotIds = Set.of(); // 防御
        }

        if (operator == OperatorType.IN) {
            for (String dayOfWeek : strings) {
                Set<Long> timeslotIds = dayOfWeekToTimeslotIds.get(dayOfWeek);
                CommonMethods.addAllIfExists(allowTimeslotIds, timeslotIds);
            }
        } else if (operator == OperatorType.NOT_IN) {
            Set<Long> forbidden = new HashSet<>();
            for (String dayOfWeek : strings) {
                Set<Long> timeslotIds = dayOfWeekToTimeslotIds.get(dayOfWeek);
                CommonMethods.addAllIfExists(forbidden, timeslotIds);
            }
            allowTimeslotIds = new HashSet<>(allTimeslotIds);
            allowTimeslotIds.removeAll(forbidden);
        }

        Map<TargetKey, Set<Long>> targetMap =
                "HARD".equalsIgnoreCase(level)
                        ? teacherAllowed.getConstrainMap()
                        : teacherAllowed.getConstrainSoftMap();

        for (int i = 0; i < teacherIds.size(); i++) {
            long teacherId = teacherIds.getLong(i);
            TargetKey targetKey = TargetKey.forTeacher(teacherId);

            targetMap.merge(
                    targetKey,
                    new LinkedHashSet<>(allowTimeslotIds),
                    (existing, incoming) -> {
                        existing.retainAll(incoming);
                        return existing;
                    }
            );
        }
    }

    public static Constrain<Long> ensureTeacherAllowedInitialized(Constrains constrains) {
        Constrain<Long> allowed = constrains.getTeacherAllowedTimeWindows();
        if (allowed == null) {
            allowed = new Constrain<>();
            allowed.setConstrainMap(new HashMap<>());
            allowed.setConstrainSoftMap(new HashMap<>());
            constrains.setTeacherAllowedTimeWindows(allowed);
        } else {
            if (allowed.getConstrainMap() == null) allowed.setConstrainMap(new HashMap<>());
            if (allowed.getConstrainSoftMap() == null) allowed.setConstrainSoftMap(new HashMap<>());
        }
        return allowed;
    }



}
